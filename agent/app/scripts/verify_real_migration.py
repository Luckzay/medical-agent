from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models.knowledge import DocumentChunk, IndexManifest, OwnershipScope
from app.scripts.migrate_literature import migrate
from app.services.embeddings import DeterministicTestEmbedding
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.vector_index import QdrantVectorStore


def verify(source: Path, database: Path) -> dict[str, object]:
    scope = OwnershipScope(tenant_id="default", project_id="literature")
    first = migrate(source, database, scope)
    second = migrate(source, database, scope)
    repository = SQLiteCanonicalRepository(database)
    rows = repository.connection.execute(
        "SELECT payload_json FROM document_chunks WHERE tenant_id=? AND project_id=? "
        "ORDER BY ordinal",
        (scope.tenant_id, scope.project_id),
    ).fetchall()
    chunks = [DocumentChunk.model_validate_json(row[0]) for row in rows]
    embedding = DeterministicTestEmbedding(32)
    manifest = IndexManifest(
        manifest_id="real-migration-test",
        collection_name="medical_evidence_v1_real_migration",
        alias="medical_evidence_active",
        generation="real-migration",
        schema_version=1,
        vector_name="dense",
        dimension=32,
        embedding_fingerprint=embedding.fingerprint,
        payload_schema_version=1,
        source_snapshot=str(first["source_sha256"]),
    )
    store = QdrantVectorStore.memory()
    vectors = embedding.embed_documents([chunk.text for chunk in chunks])
    store.upsert(manifest, chunks, vectors)
    point_count = store.count(manifest.collection_name, scope)
    evidence_rows = repository.connection.execute(
        "SELECT evidence_id FROM legacy_evidence_mappings ORDER BY evidence_id"
    ).fetchall()
    resolved = sum(bool(repository.resolve_legacy(scope, str(row[0]))) for row in evidence_rows)
    repository.close()
    return {
        "first_run": first,
        "second_run": second,
        "canonical_chunk_count": len(chunks),
        "vector_point_count": point_count,
        "legacy_resolution_count": resolved,
        "deterministic_repeat": first["document_id"] == second["document_id"]
        and first["version_id"] == second["version_id"]
        and second["created_version"] is False,
        "embedding": {
            "fingerprint": embedding.fingerprint,
            "test_only": True,
            "random_vectors": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(verify(args.source, args.database), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
