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
from app.services.knowledge_repository import MySQLCanonicalRepository
from app.services.lexical_store import ElasticsearchLexicalStore
from app.services.runtime import build_elasticsearch_client, build_runtime
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
            cursor.execute(
                "SELECT id, herb_name, "
                + ", ".join(TOXICOLOGY_FIELDS)
                + " FROM herb_basic ORDER BY id"
            )
            herbs = list(cursor.fetchall())
            cursor.execute(
                "SELECT id AS compound_id, herb_id, compound_name, "
                "molecular_formula AS formula, cas FROM herb_toxiccompound ORDER BY herb_id,id"
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


def sync_structured_mysql(
    repository: MySQLCanonicalRepository,
    records: list[dict[str, Any]],
    db_name: str,
    snapshot: str,
) -> None:
    repository.replace_toxicology_snapshot(records, db_name, snapshot)


def elasticsearch_documents(
    records: list[dict[str, Any]], scope: OwnershipScope, snapshot: str
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for record in records:
        compounds = record.get("toxic_compounds", [])
        document: dict[str, object] = {
            "reference": record["reference"],
            "herb_id": record["id"],
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "source_snapshot": snapshot,
            "name": record["herb_name"],
            "common_name": record.get("common_name") or "",
            "compound_names": [item.get("compound_name", "") for item in compounds],
            "cas_numbers": [item.get("cas", "") for item in compounds if item.get("cas")],
            "formulas": [item.get("formula", "") for item in compounds if item.get("formula")],
        }
        document.update(
            {
                field: record.get(field) or ""
                for field in TOXICOLOGY_FIELDS
                if field != "link_to_clinical_suggestion"
            }
        )
        documents.append(document)
    return documents


def build_elasticsearch_index(
    store: ElasticsearchLexicalStore,
    records: list[dict[str, Any]],
    scope: OwnershipScope,
    snapshot: str,
    generation: str,
) -> str:
    index = store.versioned_index(generation, snapshot)
    documents = elasticsearch_documents(records, scope, snapshot)
    store.create_versioned_index(index, snapshot)
    indexed = store.bulk_index(index, documents)
    expected_ids = {str(document["reference"]) for document in documents}
    if indexed != len(documents) or store.count(index) != len(documents):
        raise RuntimeError("Elasticsearch document count reconciliation failed")
    if store.document_ids(index, len(expected_ids) + 1) != expected_ids:
        raise RuntimeError("Elasticsearch document ID reconciliation failed")
    store.activate(index)
    return index


def active_chunks(
    repository: MySQLCanonicalRepository, scope: OwnershipScope
) -> list[DocumentChunk]:
    return repository.active_chunks(scope)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从业务 MySQL 构建 canonical 关系数据、Elasticsearch 与 Qdrant 索引"
    )
    parser.add_argument("--force", action="store_true", help="强制重新构建索引")
    parser.add_argument(
        "--targets",
        default="elasticsearch",
        help="逗号分隔目标：elasticsearch,qdrant；关系数据始终同步到 MySQL",
    )
    parser.add_argument("--dry-run", action="store_true", help="只读取并校验源记录")
    parser.add_argument("--generation", help="显式版本代号，默认使用 UTC 时间")
    args = parser.parse_args()
    targets = {item.strip() for item in args.targets.split(",") if item.strip()}
    unsupported = targets - {"elasticsearch", "qdrant"}
    if unsupported or not targets:
        raise SystemExit(f"invalid targets: {','.join(sorted(unsupported)) or '(empty)'}")

    settings = get_settings()
    if "qdrant" in targets and settings.vector_mode == "disabled":
        raise SystemExit("AGENT_VECTOR_MODE must be optional or required when qdrant is targeted")
    if settings.evidence_project_id != "toxicology":
        raise SystemExit("AGENT_EVIDENCE_PROJECT_ID must be toxicology")
    records, db_name = load_records()
    if not records:
        raise SystemExit("business database returned no herb toxicology records")
    snapshot = hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()
    generation = args.generation or time.strftime("%Y%m%d%H%M%S", time.gmtime())
    scope = OwnershipScope(
        tenant_id=settings.evidence_tenant_id, project_id=settings.evidence_project_id
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "records": len(records),
                    "targets": sorted(targets),
                    "generation": generation,
                    "source_snapshot": snapshot,
                    "document_ids": [record["reference"] for record in records],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    started = time.monotonic()
    repository = MySQLCanonicalRepository()
    sync_structured_mysql(repository, records, db_name, snapshot)
    runtime = build_runtime(settings)
    current_sources = {f"mysql://{db_name}/herb_basic/{record['id']}" for record in records}
    tombstoned_count = 0
    for row in repository.list_active_documents(scope):
        if row["logical_source"] not in current_sources:
            repository.tombstone(scope, str(row["document_id"]))
            tombstoned_count += 1

    ingestion = IngestionService(
        repository,
        ParserRegistry([PlainTextParser()]),
        StructureFirstChunker(
            ChunkingPolicy(
                token_budget=settings.chunk_token_budget,
                overlap=settings.chunk_token_overlap,
                version=settings.chunker_version,
            )
        ),
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
            idempotency_key=f"toxicology:{record['id']}:{hashlib.sha256(content).hexdigest()}",
        )
    herb_count, orphan_compounds = repository.toxicology_counts()
    if herb_count != len(records):
        raise RuntimeError(f"Validation failed: MySQL herb count {herb_count} != {len(records)}")
    if orphan_compounds:
        raise RuntimeError(f"Validation failed: {orphan_compounds} orphan compounds found")

    result: dict[str, object] = {
        "source": f"mysql://{db_name} herb_basic + herb_toxiccompound",
        "records": len(records),
        "tombstoned": tombstoned_count,
        "targets": sorted(targets),
        "canonical_database": settings.mysql_database,
        "source_snapshot": snapshot,
    }
    if "elasticsearch" in targets:
        lexical = ElasticsearchLexicalStore(
            build_elasticsearch_client(settings),
            settings.elasticsearch_index_alias,
            timeout_seconds=settings.elasticsearch_timeout_seconds,
        )
        result["elasticsearch_index"] = build_elasticsearch_index(
            lexical, records, scope, snapshot, generation
        )
        result["elasticsearch_alias"] = settings.elasticsearch_index_alias
    if "qdrant" in targets:
        if runtime.store is None:
            raise RuntimeError("Qdrant target selected but vector store is unavailable")
        chunks = active_chunks(repository, scope)
        if not chunks:
            raise RuntimeError("No active chunks found to build Qdrant index")
        vectors = runtime.embedding.embed_documents([chunk.text for chunk in chunks])
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
        active = IndexManager(runtime.store).rebuild(
            manifest, chunks, vectors, smoke_vector=vectors[0] if vectors else None
        )
        result.update(
            {
                "chunks": len(chunks),
                "collection": active.collection_name,
                "qdrant_alias": active.alias,
                "qdrant_status": str(active.status),
            }
        )
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
