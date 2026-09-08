from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VectorMode(StrEnum):
    DISABLED = "disabled"
    OPTIONAL = "optional"
    REQUIRED = "required"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    STRUCTURED_ROW = "structured_row"
    CAPTION = "caption"
    CODE = "code"


class IngestionStage(StrEnum):
    RECEIVED = "received"
    PARSING = "parsing"
    NORMALIZED = "normalized"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    INDEXED = "indexed"
    QUALITY_CHECKED = "quality_checked"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class ManifestStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    HEALTHY = "healthy"
    FAILED = "failed"
    RETIRED = "retired"


class OwnershipScope(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)


class SourceLocator(StrictModel):
    source_uri: str = Field(min_length=1)
    sheet: str | None = None
    row: int | None = Field(default=None, ge=1)
    page: int | None = Field(default=None, ge=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    heading_path: tuple[str, ...] = ()


class CanonicalDocument(StrictModel):
    document_id: str
    scope: OwnershipScope
    logical_source: str
    media_type: str
    status: DocumentStatus = DocumentStatus.PENDING
    active_version_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tombstoned_at: datetime | None = None


class DocumentVersion(StrictModel):
    version_id: str
    document_id: str
    scope: OwnershipScope
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_locator: SourceLocator
    media_type: str
    parser_fingerprint: str
    status: DocumentStatus = DocumentStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NormalizedBlock(StrictModel):
    block_id: str
    version_id: str
    ordinal: int = Field(ge=0)
    block_type: BlockType
    text: str
    locator: SourceLocator
    hierarchy: tuple[str, ...] = ()
    language: str | None = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(StrictModel):
    chunk_id: str
    version_id: str
    scope: OwnershipScope
    ordinal: int = Field(ge=0)
    text: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    token_count: int = Field(ge=0)
    chunker_fingerprint: str
    locator: SourceLocator
    parent_context: str | None = None
    block_ids: tuple[str, ...] = ()


class IngestionJob(StrictModel):
    job_id: str
    scope: OwnershipScope
    document_id: str
    version_id: str | None = None
    stage: IngestionStage = IngestionStage.RECEIVED
    durable_stage: IngestionStage = IngestionStage.RECEIVED
    retry_count: int = Field(default=0, ge=0)
    processed_items: int = Field(default=0, ge=0)
    total_items: int = Field(default=0, ge=0)
    error_code: str | None = None
    safe_diagnostic: str | None = Field(default=None, max_length=500)
    parser_fingerprint: str
    chunker_fingerprint: str
    embedding_fingerprint: str
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IndexManifest(StrictModel):
    manifest_id: str
    collection_name: str
    alias: str
    generation: str
    schema_version: int = Field(ge=1)
    vector_name: str
    dimension: int = Field(gt=0)
    distance: str = "cosine"
    normalized: bool = True
    embedding_fingerprint: str
    payload_schema_version: int = Field(ge=1)
    source_snapshot: str
    status: ManifestStatus = ManifestStatus.CANDIDATE
    point_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RetrievalDiagnostics(StrictModel):
    mode: str
    policy_version: str
    lexical_rank: int | None = None
    vector_rank: int | None = None
    fused_rank: int | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None
    reranker_fingerprint: str | None = None
    exact_matches: tuple[str, ...] = ()
    manifest_generation: str | None = None
    embedding_fingerprint: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    degraded_reason: str | None = None
