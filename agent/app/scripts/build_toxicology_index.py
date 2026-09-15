from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymysql  # type: ignore[import-untyped]
from dotenv import dotenv_values

from app.core.config import get_settings
from app.models.knowledge import DocumentChunk, IndexManifest, OwnershipScope
from app.services.document_processing import (
    ChunkingPolicy,
    ParserRegistry,
    PlainTextParser,
    StructureFirstChunker,
)
from app.services.ingestion import IngestionService
from app.services.knowledge_repository import _SCHEMA, SQLiteCanonicalRepository
from app.services.runtime import build_runtime
from app.services.vector_index import IndexManager

TOXICOLOGY_FIELDS = (
    "virulence",
    "toxicity_mechanism",
    "pathological_examination",
    "crowd_taboo",
    "symptom_contraindications",
    "adr",
    "typical_cases_of_adr",
    "clinical_suggestion",
    "clinical_suggestion_basis",
    "link_to_clinical_suggestion",
)
DB_ENV_KEYS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


def load_db_environment(env_file: Path | None = None) -> None:
    """Load unprefixed MySQL settings from the Agent .env without overriding real env vars."""
    path = env_file or Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    values = dotenv_values(path)
    for key in DB_ENV_KEYS:
        value = values.get(key)
        if value is not None:
            os.environ.setdefault(key, value)


def load_records() -> tuple[list[dict[str, Any]], str]:
    load_db_environment()
    db_name = os.getenv("DB_NAME", "ai_medical_db")
    connection = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            columns = "SELECT id, herb_name, " + ", ".join(TOXICOLOGY_FIELDS)
            cursor.execute(columns + " FROM herb_basic ORDER BY id")
            herbs = list(cursor.fetchall())
            cursor.execute(
                "SELECT id AS compound_id, herb_id, compound_name, "
                "molecular_formula AS formula, cas "
                "FROM herb_toxiccompound ORDER BY herb_id, id"
            )
            compounds = list(cursor.fetchall())
    finally:
        connection.close()

    by_herb: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for compound in compounds:
        by_herb[int(compound.pop("herb_id"))].append(compound)

    for herb in herbs:
        herb["reference"] = f"herb_basic:{herb['id']}"
        herb["toxic_compounds"] = by_herb[int(herb["id"])]

    return herbs, db_name


def sync_structured_sqlite(
    repository: SQLiteCanonicalRepository,
    records: list[dict[str, Any]],
    db_name: str,
    snapshot: str
) -> None:
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with repository.transaction() as db:
        # 0. Ensure schema is updated (dropping for rebuild as it's a migration/indexing script)
        db.execute("DROP TABLE IF EXISTS toxicology_fts")
        db.execute("DROP TABLE IF EXISTS toxicology_compounds")
        db.execute("DROP TABLE IF EXISTS toxicology_herbs")
        db.execute("DROP TABLE IF EXISTS toxicology_snapshots")

        # Re-run CREATE TABLE from repository schema
        for statement in _SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)

        # 1. Update snapshot
        db.execute(
            "INSERT INTO toxicology_snapshots (snapshot_id, source_snapshot, created_at) "
            "VALUES (?, ?, ?)",
            (str(uuid4()), snapshot, created_at)
        )

        # 3. Insert herbs and compounds
        for herb in records:
            herb_id = herb["id"]
            db.execute(
                "INSERT INTO toxicology_herbs (herb_id, name, common_name, "
                "logical_source, reference, "
                + ", ".join(TOXICOLOGY_FIELDS) + ", created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    herb_id,
                    herb["herb_name"],
                    herb.get("common_name"),
                    f"mysql://{db_name}/herb_basic/{herb_id}",
                    herb["reference"],
                    *[herb.get(f) for f in TOXICOLOGY_FIELDS],
                    created_at
                )
            )

            compound_names = []
            cas_numbers = []
            formulas = []
            for compound in herb["toxic_compounds"]:
                c_id = compound["compound_id"]
                c_name = compound.get("compound_name", "")
                c_formula = compound.get("formula", "")
                c_cas = compound.get("cas", "")
                c_source = f"mysql://{db_name}/herb_toxiccompound/{c_id}"

                db.execute(
                    "INSERT INTO toxicology_compounds "
                    "(compound_id, herb_id, name, formula, cas, logical_source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (c_id, herb_id, c_name, c_formula, c_cas, c_source, created_at)
                )

                if c_name:
                    compound_names.append(c_name)
                if c_cas:
                    cas_numbers.append(c_cas)
                if c_formula:
                    formulas.append(c_formula)

            # 4. Insert FTS
            fts_fields = [f for f in TOXICOLOGY_FIELDS if f != "link_to_clinical_suggestion"]
            db.execute(
                "INSERT INTO toxicology_fts (herb_id, name, common_name, "
                "virulence, toxicity_mechanism, "
                "pathological_examination, crowd_taboo, symptom_contraindications, adr, "
                "typical_cases_of_adr, clinical_suggestion, clinical_suggestion_basis, "
                "compound_names, cas_numbers, formulas) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    herb_id,
                    herb["herb_name"],
                    herb.get("common_name"),
                    *[herb.get(f) for f in fts_fields],
                    " ".join(compound_names),
                    " ".join(cas_numbers),
                    " ".join(formulas),
                )
            )


def active_chunks(
    repository: SQLiteCanonicalRepository, scope: OwnershipScope
) -> list[DocumentChunk]:
    rows = repository.connection.execute(
        "SELECT c.payload_json FROM document_chunks c "
        "JOIN document_versions v ON v.version_id=c.version_id "
        "JOIN documents d ON d.document_id=v.document_id "
        "WHERE c.tenant_id=? AND c.project_id=? AND d.status='ready' "
        "AND v.status='ready' AND d.active_version_id=v.version_id "
        "ORDER BY d.logical_source, c.ordinal",
        (scope.tenant_id, scope.project_id),
    ).fetchall()
    return [DocumentChunk.model_validate_json(row[0]) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从业务 MySQL 幂等构建 canonical SQLite + Qdrant 中药毒理索引"
    )
    parser.add_argument("--force", action="store_true", help="强制重新构建索引，即使快照未变化")
    args = parser.parse_args()

    settings = get_settings()
    if settings.vector_mode == "disabled":
        raise SystemExit("AGENT_VECTOR_MODE must be optional or required")
    if settings.evidence_project_id != "toxicology":
        raise SystemExit("AGENT_EVIDENCE_PROJECT_ID must be toxicology")

    records, db_name = load_records()
    if not records:
        raise SystemExit("business database returned no herb toxicology records")

    snapshot = hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()

    runtime = build_runtime(settings)
    assert runtime.store is not None

    active_manifest = runtime.store.active_manifest(settings.qdrant_collection_alias)
    if active_manifest and active_manifest.source_snapshot == snapshot and not args.force:
        # Check SQLite snapshot consistency
        repository = SQLiteCanonicalRepository(settings.canonical_database_path)
        row = repository.connection.execute(
            "SELECT source_snapshot FROM toxicology_snapshots"
        ).fetchone()
        if row and row[0] == snapshot:
            print(
                f"Skipping rebuild: active collection '{active_manifest.collection_name}' "
                f"is already up-to-date (snapshot {snapshot[:8]})"
            )
            return

    scope = OwnershipScope(
        tenant_id=settings.evidence_tenant_id,
        project_id=settings.evidence_project_id,
    )
    repository = SQLiteCanonicalRepository(settings.canonical_database_path)

    # 1. Sync structured SQLite (Transactional)
    sync_structured_sqlite(repository, records, db_name, snapshot)

    # 2. Tombstone removed records in generic canonical schema
    current_sources = {f"mysql://{db_name}/herb_basic/{record['id']}" for record in records}
    existing = repository.connection.execute(
        "SELECT document_id, logical_source FROM documents "
        "WHERE tenant_id=? AND project_id=? AND status != 'tombstoned'",
        (scope.tenant_id, scope.project_id),
    ).fetchall()
    tombstoned_count = 0
    for row in existing:
        if row["logical_source"] not in current_sources:
            repository.tombstone(scope, str(row["document_id"]))
            tombstoned_count += 1

    # 3. Submit records for ingestion to generic canonical schema
    chunker = StructureFirstChunker(
        ChunkingPolicy(
            token_budget=settings.chunk_token_budget,
            overlap=settings.chunk_token_overlap,
            version=settings.chunker_version,
        )
    )
    ingestion = IngestionService(
        repository,
        ParserRegistry([PlainTextParser()]),
        chunker,
        runtime.embedding,
        None,
        None,
        batch_size=settings.ingestion_batch_size,
    )
    for record in records:
        content = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str).encode()
        ingestion.submit(
            scope=scope,
            logical_source=f"mysql://{db_name}/herb_basic/{record['id']}",
            media_type="text/plain",
            content=content,
            idempotency_key=(
                f"toxicology:{record['id']}:"
                f"{hashlib.sha256(content).hexdigest()}"
            ),
        )

    # 4. Prepare Qdrant index
    chunks = active_chunks(repository, scope)
    if not chunks:
        raise SystemExit("No active chunks found to build index")

    generation = time.strftime("%Y%m%d%H%M%S")
    manifest = IndexManifest(
        manifest_id=str(uuid4()),
        collection_name=f"toxicology_v{generation}_{snapshot[:8]}",
        alias=settings.qdrant_collection_alias,
        generation=generation,
        schema_version=1,
        vector_name="dense",
        dimension=runtime.embedding.dimension,
        normalized=settings.embedding_normalize,
        embedding_fingerprint=runtime.embedding.fingerprint,
        payload_schema_version=1,
        source_snapshot=snapshot,
    )

    started = time.monotonic()
    vectors = runtime.embedding.embed_documents([chunk.text for chunk in chunks])

    # 5. Validation before publishing
    # Validate herb count
    h_count = repository.connection.execute(
        "SELECT COUNT(*) FROM toxicology_herbs"
    ).fetchone()[0]
    if h_count != len(records):
        raise RuntimeError(f"Validation failed: SQLite herb count {h_count} != {len(records)}")

    # Validate compound orphan=0
    orphan_compounds = repository.connection.execute(
        "SELECT COUNT(*) FROM toxicology_compounds "
        "WHERE herb_id NOT IN (SELECT herb_id FROM toxicology_herbs)"
    ).fetchone()[0]
    if orphan_compounds > 0:
        raise RuntimeError(f"Validation failed: {orphan_compounds} orphan compounds found")

    # Validate chunks and vectors count
    if len(chunks) != len(vectors):
        raise RuntimeError(
            f"Validation failed: chunks {len(chunks)} != vectors {len(vectors)}"
        )

    # 6. Publish Qdrant index
    active = IndexManager(runtime.store).rebuild(
        manifest, chunks, vectors, smoke_vector=vectors[0] if vectors else None
    )

    # 7. Final Snapshot Validation
    sq_snapshot = repository.connection.execute(
        "SELECT source_snapshot FROM toxicology_snapshots"
    ).fetchone()[0]
    if sq_snapshot != active.source_snapshot:
        raise RuntimeError(
            f"Validation failed: SQLite {sq_snapshot} != Qdrant {active.source_snapshot}"
        )

    result = {
        "source": f"mysql://{db_name} herb_basic + herb_toxiccompound",
        "records": len(records),
        "tombstoned": tombstoned_count,
        "chunks": len(chunks),
        "canonical_database": str(settings.canonical_database_path),
        "collection": active.collection_name,
        "alias": active.alias,
        "status": str(active.status),
        "source_snapshot": snapshot,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
