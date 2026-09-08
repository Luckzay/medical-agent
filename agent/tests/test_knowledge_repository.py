from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.models.knowledge import (
    CanonicalDocument,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    IngestionStage,
    OwnershipScope,
    SourceLocator,
)
from app.services.knowledge_repository import ImmutableVersionError, SQLiteCanonicalRepository


def version(
    scope: OwnershipScope, suffix: str, digest: str
) -> tuple[CanonicalDocument, DocumentVersion]:
    document = CanonicalDocument(
        document_id=f"doc-{suffix}",
        scope=scope,
        logical_source=f"source-{suffix}",
        media_type="text/plain",
    )
    item = DocumentVersion(
        version_id=f"ver-{suffix}-{digest[:4]}",
        document_id=document.document_id,
        scope=scope,
        source_hash=digest,
        source_locator=SourceLocator(source_uri=f"memory:{suffix}"),
        media_type="text/plain",
        parser_fingerprint="plain:v1",
    )
    return document, item


def chunk(scope: OwnershipScope, item: DocumentVersion) -> DocumentChunk:
    text = "canonical content"
    return DocumentChunk(
        chunk_id=f"chunk-{item.version_id}",
        version_id=item.version_id,
        scope=scope,
        ordinal=0,
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        token_count=2,
        chunker_fingerprint="chunk:v1",
        locator=item.source_locator,
    )


def test_repository_dedup_versions_activation_scope_and_history(tmp_path: Path) -> None:
    repo = SQLiteCanonicalRepository(tmp_path / "canonical.db")
    a = OwnershipScope(tenant_id="tenant", project_id="a")
    b = OwnershipScope(tenant_id="tenant", project_id="b")
    digest1 = hashlib.sha256(b"one").hexdigest()
    document, first = version(a, "x", digest1)
    assert repo.create_version(document, first)[1]
    assert not repo.create_version(document, first)[1]
    _, second = version(a, "x", hashlib.sha256(b"two").hexdigest())
    assert repo.create_version(document, second)[1]
    assert len(repo.list_versions(a, document.document_id)) == 2
    assert repo.list_versions(b, document.document_id) == []
    item = chunk(a, second)
    repo.put_chunks(a, [item])
    assert repo.get_chunks(a, [item.chunk_id]) == []
    repo.activate_version(a, document.document_id, second.version_id)
    assert repo.get_chunks(a, [item.chunk_id]) == [item]
    assert repo.get_chunks(b, [item.chunk_id]) == []
    repo.map_legacy("literature:EN:2", a, document.document_id, first.version_id, item.chunk_id, 2)
    assert repo.resolve_legacy(a, "literature:EN:2")[1] == first.version_id
    assert repo.tombstone(b, document.document_id) == 0
    assert repo.tombstone(a, document.document_id) == 1
    assert repo.resolve_legacy(a, "literature:EN:2")[1] == first.version_id


def test_repository_immutable_collision_and_retry_state(tmp_path: Path) -> None:
    repo = SQLiteCanonicalRepository(tmp_path / "canonical.db")
    scope = OwnershipScope(tenant_id="t", project_id="p")
    document, first = version(scope, "a", hashlib.sha256(b"a").hexdigest())
    repo.create_version(document, first)
    collision = first.model_copy(update={"source_hash": hashlib.sha256(b"b").hexdigest()})
    with pytest.raises(ImmutableVersionError):
        repo.create_version(document, collision)
    job = IngestionJob(
        job_id="job",
        scope=scope,
        document_id=document.document_id,
        stage=IngestionStage.FAILED,
        durable_stage=IngestionStage.CHUNKED,
        retry_count=1,
        error_code="EMBEDDING_INVALID",
        safe_diagnostic="invalid dimension",
        parser_fingerprint="p",
        chunker_fingerprint="c",
        embedding_fingerprint="e",
        idempotency_key="key",
    )
    repo.save_job(job)
    assert repo.get_job(scope, "job").durable_stage is IngestionStage.CHUNKED
    with pytest.raises(KeyError):
        repo.get_job(OwnershipScope(tenant_id="t", project_id="other"), "job")
