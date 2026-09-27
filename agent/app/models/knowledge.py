from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


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
    tenant_id: str = Field(
        min_length=1, max_length=128, description="租户标识符", examples=["default-tenant"]
    )
    project_id: str = Field(
        min_length=1, max_length=128, description="项目标识符", examples=["toxicology"]
    )


class SourceLocator(StrictModel):
    source_uri: str = Field(min_length=1, description="原始数据定位 URI")
    sheet: str | None = Field(default=None, description="工作表名称（针对 Excel）")
    row: int | None = Field(default=None, ge=1, description="起始行号")
    page: int | None = Field(default=None, ge=1, description="页码")
    start_line: int | None = Field(default=None, ge=1, description="起始行")
    end_line: int | None = Field(default=None, ge=1, description="结束行")
    heading_path: tuple[str, ...] = Field(default_factory=tuple, description="标题层级路径")


class CanonicalDocument(StrictModel):
    document_id: str = Field(description="文档唯一标识符")
    scope: OwnershipScope = Field(description="所属所有权范围")
    logical_source: str = Field(description="逻辑数据源标识")
    media_type: str = Field(description="媒体类型")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="文档当前状态")
    active_version_id: str | None = Field(default=None, description="当前生效的任务版本 ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")
    tombstoned_at: datetime | None = Field(default=None, description="软删除时间")


class DocumentVersion(StrictModel):
    version_id: str = Field(description="版本唯一标识符")
    document_id: str = Field(description="关联文档 ID")
    scope: OwnershipScope = Field(description="所属所有权范围")
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="源内容 SHA-256 哈希")
    source_locator: SourceLocator = Field(description="源数据定位信息")
    media_type: str = Field(description="媒体类型")
    parser_fingerprint: str = Field(description="解析器指纹")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="版本状态")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")


class NormalizedBlock(StrictModel):
    block_id: str = Field(description="块唯一标识符")
    version_id: str = Field(description="关联版本 ID")
    ordinal: int = Field(ge=0, description="块在文档中的序号")
    block_type: BlockType = Field(description="块类型（标题、段落等）")
    text: str = Field(description="块文本内容")
    locator: SourceLocator = Field(description="源定位信息")
    hierarchy: tuple[str, ...] = Field(default_factory=tuple, description="文档层级")
    language: str | None = Field(default=None, description="识别出的语言")
    warnings: tuple[str, ...] = Field(default_factory=tuple, description="处理警告")
    metadata: dict[str, Any] = Field(default_factory=dict, description="其他元数据")


class DocumentChunk(StrictModel):
    chunk_id: str = Field(description="切片唯一标识符")
    version_id: str = Field(description="关联版本 ID")
    scope: OwnershipScope = Field(description="所属所有权范围")
    ordinal: int = Field(ge=0, description="切片序号")
    text: str = Field(description="切片内容")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="切片内容哈希")
    token_count: int = Field(ge=0, description="Token 数量")
    chunker_fingerprint: str = Field(description="切片器指纹")
    locator: SourceLocator = Field(description="源定位信息")
    parent_context: str | None = Field(default=None, description="父级上下文描述")
    block_ids: tuple[str, ...] = Field(default_factory=tuple, description="关联的原始块 ID 列表")


class IngestionJob(StrictModel):
    job_id: str = Field(description="入库任务 ID")
    scope: OwnershipScope = Field(description="所属所有权范围")
    document_id: str = Field(description="关联文档 ID")
    version_id: str | None = Field(default=None, description="生成的版本 ID")
    stage: IngestionStage = Field(default=IngestionStage.RECEIVED, description="当前处理阶段")
    durable_stage: IngestionStage = Field(
        default=IngestionStage.RECEIVED, description="已持久化的处理阶段"
    )
    retry_count: int = Field(default=0, ge=0, description="重试次数")
    processed_items: int = Field(default=0, ge=0, description="已处理条目数")
    total_items: int = Field(default=0, ge=0, description="总条目数")
    error_code: str | None = Field(default=None, description="错误代码")
    safe_diagnostic: str | None = Field(
        default=None, max_length=500, description="脱敏后的诊断信息"
    )
    parser_fingerprint: str = Field(description="解析器配置指纹")
    chunker_fingerprint: str = Field(description="切片器配置指纹")
    embedding_fingerprint: str = Field(description="向量模型指纹")
    idempotency_key: str = Field(description="幂等键")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="最后更新时间"
    )


class IndexManifest(StrictModel):
    manifest_id: str = Field(description="清单唯一标识符")
    collection_name: str = Field(description="底层的向量集合名称")
    alias: str = Field(description="集合别名")
    generation: str = Field(description="索引代号")
    schema_version: int = Field(ge=1, description="模式版本")
    vector_name: str = Field(description="向量字段名称")
    dimension: int = Field(gt=0, description="向量维度")
    distance: str = Field(default="cosine", description="距离度量指标")
    normalized: bool = Field(default=True, description="是否经过归一化")
    embedding_fingerprint: str = Field(description="关联的 Embedding 模型指纹")
    payload_schema_version: int = Field(ge=1, description="Payload 模式版本")
    source_snapshot: str = Field(description="数据源快照标识")
    status: ManifestStatus = Field(default=ManifestStatus.CANDIDATE, description="清单状态")
    point_count: int = Field(default=0, ge=0, description="索引包含的点数量")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")


class RetrievalDiagnostics(StrictModel):
    mode: str = Field(description="检索模式")
    policy_version: str = Field(description="策略版本")
    lexical_rank: int | None = Field(default=None, description="词法检索排名")
    vector_rank: int | None = Field(default=None, description="向量检索排名")
    fused_rank: int | None = Field(default=None, description="融合检索排名")
    rerank_rank: int | None = Field(default=None, description="重排序排名")
    rerank_score: float | None = Field(default=None, description="重排序分数")
    reranker_fingerprint: str | None = Field(default=None, description="重排序模型指纹")
    exact_matches: tuple[str, ...] = Field(default_factory=tuple, description="精确匹配项")
    manifest_generation: str | None = Field(default=None, description="清单代号")
    embedding_fingerprint: str | None = Field(default=None, description="Embedding 指纹")
    latency_ms: float = Field(default=0.0, ge=0.0, description="耗时（毫秒）")
    degraded_reason: str | None = Field(default=None, description="降级原因")
    lexical_backend: str | None = Field(default=None, description="词法检索后端")
    retrieval_sources: tuple[str, ...] = Field(default_factory=tuple, description="实际检索数据源")
    source_snapshot: str | None = Field(default=None, description="词法索引数据源快照")


class IngestionResponse(ResponseModel):
    job_id: str = Field(description="已接收的入库任务 ID")
    stage: IngestionStage = Field(description="初始处理阶段")
    accepted: bool = Field(default=True, description="任务是否已被成功接收")


class DeleteDocumentResponse(ResponseModel):
    deleted: bool = Field(description="文档是否已成功删除（或标记为删除）")


class ReprocessDocumentResponse(ResponseModel):
    accepted: bool = Field(default=True, description="重处理请求是否已接收")
    document_id: str = Field(description="文档标识符")
    idempotency_key_hash: str = Field(description="幂等键哈希摘要（前16位）")


class IndexStatusResponse(ResponseModel):
    vector_mode: str = Field(description="当前的向量化工作模式")
    manifests: list[IndexManifest] = Field(description="当前存在的索引清单列表")
    degraded: bool = Field(description="系统是否处于降级运行模式")


class ToxicologyRetrievalStatusResponse(ResponseModel):
    lexical_backend: str = Field(description="配置的毒理词法检索后端")
    active_lexical_backend: str | None = Field(default=None, description="当前可用词法后端")
    lexical_health: dict[str, object] = Field(description="词法后端健康信息")
    vector_mode: str = Field(description="毒理向量检索模式")
    qdrant_alias: str = Field(description="毒理 Qdrant alias")
    vector_health: dict[str, object] = Field(description="毒理向量后端健康信息")
    degraded: bool = Field(description="毒理检索是否处于降级状态")
    degradation: list[str] = Field(default_factory=list, description="毒理检索降级原因")


class IndexOperationResponse(ResponseModel):
    accepted: bool = Field(default=True, description="索引操作请求是否已接收")
    operation: str = Field(description="操作类型（如 rebuild, rollback, reconcile）")
    scope: OwnershipScope = Field(description="操作的作用域范围")
    request_hash: str | None = Field(default=None, description="请求哈希标识（仅针对部分操作）")


class DiagnosticsResponse(ResponseModel):
    query_length: int = Field(description="查询文本长度")
    filter_names: list[str] = Field(description="使用的过滤器名称列表")
    scope: OwnershipScope = Field(description="诊断作用域")
    status: str = Field(description="诊断服务状态")
    degraded_reason: str | None = Field(default=None, description="降级原因")
    message: str = Field(description="诊断提示信息（例如超分子功能禁用的说明）")
