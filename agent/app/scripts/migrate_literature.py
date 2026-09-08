from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.models.knowledge import CanonicalDocument, DocumentVersion, OwnershipScope, SourceLocator
from app.services.document_processing import (
    ChunkingPolicy,
    StructureFirstChunker,
    literature_blocks,
)
from app.services.evidence_importer import source_sha256
from app.services.knowledge_repository import SQLiteCanonicalRepository


def migrate(source: Path, database: Path, scope: OwnershipScope) -> dict[str, object]:
    digest = source_sha256(source)
    document_id = str(
        uuid5(NAMESPACE_URL, f"{scope.tenant_id}|{scope.project_id}|{source.resolve()}")
    )
    version_id = str(uuid5(NAMESPACE_URL, f"{document_id}|{digest}"))
    repository = SQLiteCanonicalRepository(database)
    document = CanonicalDocument(
        document_id=document_id,
        scope=scope,
        logical_source=str(source),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        scope=scope,
        source_hash=digest,
        source_locator=SourceLocator(source_uri=str(source)),
        media_type=document.media_type,
        parser_fingerprint="excel-literature:v1",
    )
    _, created = repository.create_version(document, version)
    blocks, mappings = literature_blocks(source, version_id)
    repository.put_blocks(scope, blocks)
    chunks = StructureFirstChunker(ChunkingPolicy()).chunk(blocks, scope)
    repository.put_chunks(scope, chunks)
    repository.activate_version(scope, document_id, version_id)
    chunk_by_block = {chunk.block_ids[0]: chunk for chunk in chunks}
    for evidence_id, block_id in mappings.items():
        chunk = chunk_by_block[block_id]
        repository.map_legacy(
            evidence_id, scope, document_id, version_id, chunk.chunk_id, int(chunk.locator.row or 0)
        )
    resolved = sum(
        repository.resolve_legacy(scope, evidence_id)[1] == version_id for evidence_id in mappings
    )
    result = {
        "source_sha256": digest,
        "created_version": created,
        "documents": 1,
        "versions": 1,
        "blocks": len(blocks),
        "chunks": len(chunks),
        "legacy_mappings": len(mappings),
        "resolved_mappings": resolved,
        "document_id": document_id,
        "version_id": version_id,
    }
    repository.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy literature into canonical knowledge records"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--project", default="literature")
    arguments = parser.parse_args()
    print(
        json.dumps(
            migrate(
                arguments.source,
                arguments.database,
                OwnershipScope(tenant_id=arguments.tenant, project_id=arguments.project),
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
