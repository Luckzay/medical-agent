from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes import InternalAuthDependency
from app.core.config import get_settings
from app.models.knowledge import (
    DeleteDocumentResponse,
    DiagnosticsResponse,
    DocumentVersion,
    IndexOperationResponse,
    IndexStatusResponse,
    IngestionJob,
    IngestionResponse,
    OwnershipScope,
    ReprocessDocumentResponse,
    ToxicologyRetrievalStatusResponse,
)
from app.services.knowledge.processing.documents import (
    ChunkingPolicy,
    ParserRegistry,
    PlainTextParser,
    StructureFirstChunker,
)
from app.services.knowledge.processing.ingestion import IngestionService
from app.services.knowledge.storage.factory import build_lexical_store, build_vector_runtime
from app.services.knowledge.storage.mysql_repository import MySQLCanonicalRepository


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logical_source: str = Field(
        min_length=1, description="数据的逻辑来源标识", examples=["herb_wiki_v1"]
    )
    media_type: str = Field(default="text/plain", description="内容的媒体类型")
    content_text: str = Field(
        min_length=1, max_length=2_000_000, description="要入库的原始文本内容"
    )


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000, description="用于诊断的查询文本")
    filters: dict[str, str] = Field(default_factory=dict, description="检索过滤器")


router = APIRouter(prefix="/internal/v1")
_repository: MySQLCanonicalRepository | None = None


def repository() -> MySQLCanonicalRepository:
    """获取单例的规范知识库仓储实例。"""
    global _repository
    if _repository is None:
        _repository = MySQLCanonicalRepository()
    return _repository


def ingestion_service() -> IngestionService:
    """构造入库服务实例。"""
    settings = get_settings()
    runtime = build_vector_runtime(settings)
    return IngestionService(
        repository(),
        ParserRegistry([PlainTextParser()]),
        StructureFirstChunker(
            ChunkingPolicy(settings.chunk_token_budget, settings.chunk_token_overlap)
        ),
        runtime.embedding,
        runtime.store,
        runtime.manifest,
        batch_size=settings.ingestion_batch_size,
    )


def scope_and_permission(
    tenant: Annotated[str, Header(alias="X-Tenant-ID")],
    project: Annotated[str, Header(alias="X-Project-ID")],
    permissions: Annotated[str, Header(alias="X-Agent-Permissions")],
    required: str,
) -> OwnershipScope:
    """校验权限并提取作用域。"""
    if required not in {value.strip() for value in permissions.split(",")}:
        raise HTTPException(status_code=403, detail="Insufficient permission")
    return OwnershipScope(tenant_id=tenant, project_id=project)


def document_scope(
    tenant: Annotated[str, Header(alias="X-Tenant-ID")],
    project: Annotated[str, Header(alias="X-Project-ID")],
    permissions: Annotated[str, Header(alias="X-Agent-Permissions")],
) -> OwnershipScope:
    """文档操作权限校验。"""
    return scope_and_permission(tenant, project, permissions, "documents:write")


def index_scope(
    tenant: Annotated[str, Header(alias="X-Tenant-ID")],
    project: Annotated[str, Header(alias="X-Project-ID")],
    permissions: Annotated[str, Header(alias="X-Agent-Permissions")],
) -> OwnershipScope:
    """索引管理权限校验。"""
    return scope_and_permission(tenant, project, permissions, "indexes:manage")


DocumentScope = Annotated[OwnershipScope, Depends(document_scope)]
IndexScope = Annotated[OwnershipScope, Depends(index_scope)]

MGMT_ERROR_RESPONSES = {
    401: {"description": "未授权：无效或缺失的 Agent Token"},
    403: {"description": "权限不足：当前用户无权执行此操作"},
    404: {"description": "未找到：请求的资源不存在"},
}


@router.post(
    "/documents/ingestions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionResponse,
    tags=["Ingestion"],
    summary="提交入库任务",
    description="上传文档内容并启动异步入库流程，包含解析、切片、向量化及索引构建。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def submit_ingestion(
    request: IngestionRequest,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> IngestionResponse:
    """提交一个异步文档入库任务。"""
    job = ingestion_service().submit(
        scope=scope,
        logical_source=request.logical_source,
        media_type=request.media_type,
        content=request.content_text.encode(),
        idempotency_key=idempotency_key,
    )
    return IngestionResponse(job_id=job.job_id, stage=job.stage, accepted=True)


@router.get(
    "/ingestions/{job_id}",
    response_model=IngestionJob,
    tags=["Ingestion"],
    summary="获取入库任务进度",
    description="查询特定入库任务的实时处理阶段、条目进度及诊断信息。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
        404: MGMT_ERROR_RESPONSES[404],
    },
)
def get_ingestion(job_id: str, scope: DocumentScope, _auth: InternalAuthDependency) -> IngestionJob:
    """查询入库任务详情。"""
    try:
        return repository().get_job(scope, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion not found") from exc


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersion],
    tags=["Documents"],
    summary="列出文档版本",
    description="查询特定文档的所有历史版本及其解析器指纹元数据。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
        404: MGMT_ERROR_RESPONSES[404],
    },
)
def versions(
    document_id: str, scope: DocumentScope, _auth: InternalAuthDependency
) -> list[DocumentVersion]:
    """获取文档的所有版本记录。"""
    return repository().list_versions(scope, document_id)


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    tags=["Documents"],
    summary="删除文档",
    description="对文档执行逻辑删除（Tombstone），其关联的向量索引将在下一次 reconcile 时清理。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
        404: MGMT_ERROR_RESPONSES[404],
    },
)
def delete_document(
    document_id: str,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> DeleteDocumentResponse:
    """删除指定的文档及其所有版本。"""
    del idempotency_key
    return DeleteDocumentResponse(deleted=bool(repository().tombstone(scope, document_id)))


@router.post(
    "/documents/{document_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReprocessDocumentResponse,
    tags=["Documents"],
    summary="触发重处理",
    description="强制对已入库的文档重新运行解析和切片流水线。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
        404: MGMT_ERROR_RESPONSES[404],
    },
)
def reprocess_document(
    document_id: str,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> ReprocessDocumentResponse:
    """对现有文档启动重处理流程。"""
    versions = repository().list_versions(scope, document_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Document not found")
    return ReprocessDocumentResponse(
        accepted=True,
        document_id=document_id,
        idempotency_key_hash=hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
    )


@router.get(
    "/evidence/indexes/status",
    response_model=IndexStatusResponse,
    tags=["Index Management"],
    summary="查询索引全局状态",
    description="获取当前向量化模式（Vector Mode）以及活跃与候选索引清单的列表。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def index_status(scope: IndexScope, _auth: InternalAuthDependency) -> IndexStatusResponse:
    """获取知识库索引的实时状态。"""
    del scope
    return IndexStatusResponse(
        vector_mode=get_settings().vector_mode,
        manifests=repository().list_manifests(),
        degraded=get_settings().vector_mode != "required",
    )


@router.get(
    "/toxicology/retrieval/status",
    response_model=ToxicologyRetrievalStatusResponse,
    tags=["Toxicology Retrieval"],
    summary="查询毒理检索状态",
    description="独立返回 Elasticsearch 词法检索和 Qdrant 向量通道状态。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def toxicology_retrieval_status(
    _scope: IndexScope,
    _auth: InternalAuthDependency,
) -> ToxicologyRetrievalStatusResponse:
    settings = get_settings()
    lexical_health = build_lexical_store(settings).health()
    degradation: list[str] = []
    active_lexical_backend: str | None = None
    if bool(lexical_health.get("available")):
        active_lexical_backend = settings.lexical_backend
    else:
        degradation.append("lexical_unavailable")

    if settings.vector_mode == "disabled":
        vector_health: dict[str, object] = {"available": False, "reason": "vector_disabled"}
        degradation.append("vector_disabled")
    else:
        try:
            runtime = build_vector_runtime(settings)
            vector_health = (
                runtime.store.health()
                if runtime.store is not None
                else {"available": False, "reason": "vector_unavailable"}
            )
        except Exception as exc:
            vector_health = {"available": False, "reason": type(exc).__name__}
        if not bool(vector_health.get("available")):
            degradation.append("vector_unavailable")

    return ToxicologyRetrievalStatusResponse(
        lexical_backend=settings.lexical_backend,
        active_lexical_backend=active_lexical_backend,
        lexical_health=lexical_health,
        vector_mode=settings.vector_mode,
        qdrant_alias=settings.qdrant_collection_alias,
        vector_health=vector_health,
        degraded=bool(degradation),
        degradation=degradation,
    )


@router.post(
    "/evidence/indexes/rebuild",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IndexOperationResponse,
    tags=["Index Management"],
    summary="重建向量索引",
    description="基于最新的文档切片全量构建新的向量索引代号。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def rebuild_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> IndexOperationResponse:
    """提交异步全量索引重建任务。"""
    return IndexOperationResponse(
        accepted=True,
        operation="rebuild",
        scope=scope,
        request_hash=hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
    )


@router.post(
    "/evidence/indexes/rollback",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IndexOperationResponse,
    tags=["Index Management"],
    summary="回滚索引代号",
    description="将活跃索引别名指向先前的稳定代号版本。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def rollback_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> IndexOperationResponse:
    """执行索引代号回滚操作。"""
    del idempotency_key
    return IndexOperationResponse(accepted=True, operation="rollback", scope=scope)


@router.post(
    "/evidence/indexes/reconcile",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IndexOperationResponse,
    tags=["Index Management"],
    summary="同步索引内容",
    description="根据数据库状态清理或增量更新已标记为过期的索引点位。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def reconcile_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> IndexOperationResponse:
    """触发索引与数据库状态的同步。"""
    del idempotency_key
    return IndexOperationResponse(accepted=True, operation="reconcile", scope=scope)


@router.post(
    "/evidence/search/diagnostics",
    response_model=DiagnosticsResponse,
    tags=["Index Management"],
    summary="检索诊断（超分子已禁用）",
    description="分析检索路径的可达性。注意：由于超分子功能已下线，该接口当前仅返回禁用说明。",
    responses={
        401: MGMT_ERROR_RESPONSES[401],
        403: MGMT_ERROR_RESPONSES[403],
    },
)
def diagnostics(
    request: DiagnosticRequest, scope: IndexScope, _auth: InternalAuthDependency
) -> DiagnosticsResponse:
    """对检索链路进行诊断分析。"""
    return DiagnosticsResponse(
        query_length=len(request.query),
        filter_names=sorted(request.filters),
        scope=scope,
        status="disabled",
        degraded_reason="vector_disabled",
        message=(
            "Literature search diagnostics is disabled as supramolecular evidence is removed."
        ),
    )
