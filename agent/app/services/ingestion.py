from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.models.knowledge import (
    CanonicalDocument,
    DocumentVersion,
    IndexManifest,
    IngestionJob,
    IngestionStage,
    OwnershipScope,
    SourceLocator,
)
from app.services.document_processing import ParserRegistry, StructureFirstChunker
from app.services.embeddings import EmbeddingValidationError
from app.services.knowledge_observability import metrics
from app.services.knowledge_ports import EmbeddingProvider
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.vector_index import QdrantVectorStore

_STAGE_ORDER = [
    IngestionStage.RECEIVED,
    IngestionStage.PARSING,
    IngestionStage.NORMALIZED,
    IngestionStage.CHUNKED,
    IngestionStage.EMBEDDED,
    IngestionStage.INDEXED,
    IngestionStage.QUALITY_CHECKED,
    IngestionStage.READY,
]


def safe_diagnostic(exc: Exception) -> str:
    return f"{type(exc).__name__}: operation failed"[:500]


class IngestionService:
    def __init__(
        self,
        repository: SQLiteCanonicalRepository,
        parsers: ParserRegistry,
        chunker: StructureFirstChunker,
        embedding: EmbeddingProvider,
        vector_store: QdrantVectorStore | None,
        manifest: IndexManifest | None,
        *,
        batch_size: int = 32,
        stage_hook: Callable[[IngestionStage], None] | None = None,
    ) -> None:
        self.repository, self.parsers, self.chunker = repository, parsers, chunker
        self.embedding, self.vector_store, self.manifest = embedding, vector_store, manifest
        self.batch_size, self.stage_hook = batch_size, stage_hook

    def submit(
        self,
        *,
        scope: OwnershipScope,
        logical_source: str,
        media_type: str,
        content: bytes,
        idempotency_key: str,
    ) -> IngestionJob:
        source_hash = hashlib.sha256(content).hexdigest()
        document_id = str(
            uuid5(NAMESPACE_URL, f"{scope.tenant_id}|{scope.project_id}|{logical_source}")
        )
        version_id = str(uuid5(NAMESPACE_URL, f"{document_id}|{source_hash}"))
        parser = self.parsers.get(media_type)
        existing = self.repository.connection.execute(
            "SELECT payload_json FROM ingestion_jobs WHERE tenant_id=? AND project_id=? "
            "AND idempotency_key=?",
            (scope.tenant_id, scope.project_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            return IngestionJob.model_validate_json(existing[0])
        document = CanonicalDocument(
            document_id=document_id,
            scope=scope,
            logical_source=logical_source,
            media_type=media_type,
        )
        version = DocumentVersion(
            version_id=version_id,
            document_id=document_id,
            scope=scope,
            source_hash=source_hash,
            source_locator=SourceLocator(source_uri=logical_source),
            media_type=media_type,
            parser_fingerprint=parser.fingerprint,
        )
        self.repository.create_version(document, version)
        job = IngestionJob(
            job_id=str(uuid4()),
            scope=scope,
            document_id=document_id,
            version_id=version_id,
            parser_fingerprint=parser.fingerprint,
            chunker_fingerprint=self.chunker.fingerprint,
            embedding_fingerprint=self.embedding.fingerprint,
            idempotency_key=idempotency_key,
        )
        self.repository.save_job(job)
        return self.run(job, content)

    def run(self, job: IngestionJob, content: bytes) -> IngestionJob:
        parser = self.parsers.get(
            self.repository.get_version(job.scope, str(job.version_id)).media_type
        )
        try:
            job = self._transition(job, IngestionStage.PARSING)
            blocks = parser.parse(
                content,
                str(job.version_id),
                self.repository.get_version(
                    job.scope, str(job.version_id)
                ).source_locator.source_uri,
            )
            self.repository.put_blocks(job.scope, blocks)
            job = self._transition(job, IngestionStage.NORMALIZED, len(blocks), len(blocks))
            chunks = self.chunker.chunk(blocks, job.scope)
            self.repository.put_chunks(job.scope, chunks)
            job = self._transition(job, IngestionStage.CHUNKED, len(chunks), len(chunks))
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), self.batch_size):
                batch = chunks[start : start + self.batch_size]
                batch_vectors = self.embedding.embed_documents([chunk.text for chunk in batch])
                metrics.increment("embedding_calls")
                metrics.increment("embedded_documents", len(batch))
                if len(batch_vectors) != len(batch) or any(
                    len(vector) != self.embedding.dimension for vector in batch_vectors
                ):
                    raise EmbeddingValidationError("invalid embedding response")
                vectors.extend(batch_vectors)
                for chunk, vector in zip(batch, batch_vectors, strict=True):
                    self.repository.cache_embedding(
                        chunk.content_hash, self.embedding.fingerprint, vector
                    )
            job = self._transition(job, IngestionStage.EMBEDDED, len(vectors), len(chunks))
            if self.vector_store is not None and self.manifest is not None:
                self.vector_store.upsert(self.manifest, chunks, vectors)
            job = self._transition(job, IngestionStage.INDEXED, len(chunks), len(chunks))
            if not chunks or len(vectors) != len(chunks):
                raise ValueError("quality validation failed")
            job = self._transition(job, IngestionStage.QUALITY_CHECKED, len(chunks), len(chunks))
            self.repository.activate_version(job.scope, job.document_id, str(job.version_id))
            return self._transition(job, IngestionStage.READY, len(chunks), len(chunks))
        except Exception as exc:
            failed = job.model_copy(
                update={
                    "stage": IngestionStage.FAILED,
                    "retry_count": job.retry_count + 1,
                    "error_code": type(exc).__name__.upper(),
                    "safe_diagnostic": safe_diagnostic(exc),
                    "updated_at": datetime.now(UTC),
                }
            )
            self.repository.save_job(failed)
            return failed

    def retry(self, scope: OwnershipScope, job_id: str, content: bytes) -> IngestionJob:
        job = self.repository.get_job(scope, job_id)
        if job.stage is not IngestionStage.FAILED:
            return job
        return self.run(
            job.model_copy(
                update={"stage": job.durable_stage, "error_code": None, "safe_diagnostic": None}
            ),
            content,
        )

    def earliest_invalidated_stage(
        self, job: IngestionJob, *, parser: str, chunker: str, embedding: str
    ) -> IngestionStage:
        if parser != job.parser_fingerprint:
            return IngestionStage.PARSING
        if chunker != job.chunker_fingerprint:
            return IngestionStage.NORMALIZED
        if embedding != job.embedding_fingerprint:
            return IngestionStage.CHUNKED
        return job.durable_stage

    def tombstone(self, scope: OwnershipScope, document_id: str) -> int:
        changed = self.repository.tombstone(scope, document_id)
        if changed and self.vector_store is not None and self.manifest is not None:
            self.vector_store.delete(self.manifest.alias, scope, document_id=document_id)
        return changed

    def _transition(
        self, job: IngestionJob, stage: IngestionStage, processed: int = 0, total: int = 0
    ) -> IngestionJob:
        if self.stage_hook is not None:
            self.stage_hook(stage)
        current = _STAGE_ORDER.index(stage)
        durable = (
            _STAGE_ORDER[max(0, current - 1)]
            if stage not in {IngestionStage.READY, IngestionStage.RECEIVED}
            else stage
        )
        updated = job.model_copy(
            update={
                "stage": stage,
                "durable_stage": durable,
                "processed_items": processed,
                "total_items": total,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save_job(updated)
        metrics.increment(f"ingestion_stage_{stage.value}")
        metrics.gauge("ingestion_queue_depth", 0)
        return updated
