from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from app.core.config import get_settings
from app.models.knowledge import DocumentChunk, OwnershipScope
from app.scripts.migrate_literature import migrate
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.runtime import build_runtime
from app.services.vector_index import IndexManager


def chunks_from(
    repository: SQLiteCanonicalRepository, scope: OwnershipScope
) -> list[DocumentChunk]:
    rows = repository.connection.execute(
        "SELECT payload_json FROM document_chunks "
        "WHERE tenant_id=? AND project_id=? ORDER BY ordinal",
        (scope.tenant_id, scope.project_id),
    ).fetchall()
    return [DocumentChunk.model_validate_json(row[0]) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/query the production Qdrant evidence index")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    settings = get_settings()
    if settings.vector_mode == "disabled":
        raise SystemExit("AGENT_VECTOR_MODE must be optional or required")
    scope = OwnershipScope(tenant_id="default", project_id="literature")
    source = args.source or settings.evidence_source_path
    migration = migrate(source, settings.canonical_database_path, scope)
    repository = SQLiteCanonicalRepository(settings.canonical_database_path)
    chunks = chunks_from(repository, scope)
    runtime = build_runtime(settings)
    assert runtime.store is not None and runtime.manifest is not None
    manifest = runtime.manifest.model_copy(
        update={"source_snapshot": str(migration["source_sha256"])}
    )
    started = time.monotonic()
    vectors = runtime.embedding.embed_documents([chunk.text for chunk in chunks])
    embedding_seconds = time.monotonic() - started
    active = IndexManager(runtime.store).rebuild(
        manifest, chunks, vectors, smoke_vector=vectors[0] if vectors else None
    )
    query_results: dict[str, object] = {}
    for query in args.query:
        hits = runtime.store.search(
            active.alias, runtime.embedding.embed_query(query), scope, args.top_k
        )
        by_id = {
            chunk.chunk_id: chunk
            for chunk in repository.get_chunks(scope, [h.chunk_id for h in hits])
        }
        query_results[query] = [
            {
                "score": hit.score,
                "chunk_id": hit.chunk_id,
                "point_id": hit.point_id,
                "source_uri": by_id[hit.chunk_id].locator.source_uri,
                "version_id": by_id[hit.chunk_id].version_id,
                "content_hash": by_id[hit.chunk_id].content_hash,
                "text": by_id[hit.chunk_id].text[:300],
            }
            for hit in hits
        ]
    print(
        json.dumps(
            {
                "collection": active.collection_name,
                "alias": active.alias,
                "point_count": runtime.store.count(active.collection_name),
                "embedding_fingerprint": runtime.embedding.fingerprint,
                "embedding_seconds": round(embedding_seconds, 3),
                "queries": query_results,
                "idempotency_key": hashlib.sha256(
                    (active.collection_name + active.source_snapshot).encode()
                ).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
