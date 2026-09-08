from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from app.models.knowledge import IngestionStage, OwnershipScope
from app.services.document_processing import (
    ChunkingPolicy,
    ParserRegistry,
    PlainTextParser,
    StructureFirstChunker,
)
from app.services.embeddings import DeterministicTestEmbedding
from app.services.ingestion import IngestionService
from app.services.knowledge_repository import SQLiteCanonicalRepository


def service(
    tmp_path: Path, hook: Callable[[IngestionStage], None] | None = None
) -> IngestionService:
    return IngestionService(
        SQLiteCanonicalRepository(tmp_path / "ingestion.db"),
        ParserRegistry([PlainTextParser()]),
        StructureFirstChunker(ChunkingPolicy(token_budget=5, overlap=1)),
        DeterministicTestEmbedding(8),
        None,
        None,
        batch_size=2,
        stage_hook=hook,
    )


def test_ingestion_idempotency_replacement_and_scoped_tombstone(tmp_path: Path) -> None:
    ingest = service(tmp_path)
    scope = OwnershipScope(tenant_id="t", project_id="p")
    first = ingest.submit(
        scope=scope,
        logical_source="memory:doc",
        media_type="text/plain",
        content=b"one two three",
        idempotency_key="key-1",
    )
    assert first.stage is IngestionStage.READY
    same = ingest.submit(
        scope=scope,
        logical_source="memory:doc",
        media_type="text/plain",
        content=b"one two three",
        idempotency_key="key-1",
    )
    assert same.job_id == first.job_id
    replacement = ingest.submit(
        scope=scope,
        logical_source="memory:doc",
        media_type="text/plain",
        content=b"changed content now",
        idempotency_key="key-2",
    )
    assert replacement.stage is IngestionStage.READY and replacement.version_id != first.version_id
    assert ingest.repository.get_version(scope, str(first.version_id)).status.value == "superseded"
    assert (
        ingest.tombstone(OwnershipScope(tenant_id="t", project_id="other"), first.document_id) == 0
    )
    assert ingest.tombstone(scope, first.document_id) == 1


def test_failure_retry_safe_diagnostic_and_fingerprint_boundaries(tmp_path: Path) -> None:
    failed_once = True

    def hook(stage: IngestionStage) -> None:
        nonlocal failed_once
        if failed_once and stage is IngestionStage.EMBEDDED:
            failed_once = False
            raise ConnectionError("secret-token-must-not-leak")

    ingest = service(tmp_path, hook)
    scope = OwnershipScope(tenant_id="t", project_id="p")
    failed = ingest.submit(
        scope=scope,
        logical_source="memory:fail",
        media_type="text/plain",
        content=b"one two three four five six",
        idempotency_key="failure",
    )
    assert failed.stage is IngestionStage.FAILED
    assert "secret-token" not in str(failed.safe_diagnostic)
    ready = ingest.retry(scope, failed.job_id, b"one two three four five six")
    assert ready.stage is IngestionStage.READY and ready.retry_count == 1
    assert (
        ingest.earliest_invalidated_stage(
            ready,
            parser="new",
            chunker=ready.chunker_fingerprint,
            embedding=ready.embedding_fingerprint,
        )
        is IngestionStage.PARSING
    )
    assert (
        ingest.earliest_invalidated_stage(
            ready,
            parser=ready.parser_fingerprint,
            chunker="new",
            embedding=ready.embedding_fingerprint,
        )
        is IngestionStage.NORMALIZED
    )
    assert (
        ingest.earliest_invalidated_stage(
            ready,
            parser=ready.parser_fingerprint,
            chunker=ready.chunker_fingerprint,
            embedding="new",
        )
        is IngestionStage.CHUNKED
    )


def test_parser_and_invalid_vector_failures_are_durable(tmp_path: Path) -> None:
    scope = OwnershipScope(tenant_id="t", project_id="p")

    def parser_failure(stage: IngestionStage) -> None:
        if stage is IngestionStage.PARSING:
            raise ValueError("raw external payload must not leak")

    parsing = service(tmp_path / "parser", parser_failure)
    failed = parsing.submit(
        scope=scope,
        logical_source="memory:parser",
        media_type="text/plain",
        content=b"content",
        idempotency_key="parser",
    )
    assert failed.stage is IngestionStage.FAILED and failed.durable_stage is IngestionStage.RECEIVED
    assert "raw external" not in str(failed.safe_diagnostic)

    class InvalidEmbedding(DeterministicTestEmbedding):
        def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
            return [[1.0] for _ in texts]

    invalid = IngestionService(
        SQLiteCanonicalRepository(tmp_path / "vector.db"),
        ParserRegistry([PlainTextParser()]),
        StructureFirstChunker(),
        InvalidEmbedding(8),
        None,
        None,
    )
    vector_failed = invalid.submit(
        scope=scope,
        logical_source="memory:vector",
        media_type="text/plain",
        content=b"content here",
        idempotency_key="vector",
    )
    assert vector_failed.stage is IngestionStage.FAILED
    assert vector_failed.error_code == "EMBEDDINGVALIDATIONERROR"
