from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes import InternalAuthDependency
from app.core.config import get_settings
from app.models.evidence import LiteratureSearchInput
from app.models.knowledge import OwnershipScope
from app.services.document_processing import (
    ChunkingPolicy,
    ParserRegistry,
    PlainTextParser,
    StructureFirstChunker,
)
from app.services.evidence_retrieval import get_retrieval_service
from app.services.ingestion import IngestionService
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.runtime import build_runtime


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    logical_source: str = Field(min_length=1)
    media_type: str = "text/plain"
    content_text: str = Field(min_length=1, max_length=2_000_000)


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    filters: dict[str, str] = Field(default_factory=dict)


router = APIRouter(prefix="/internal/v1")
_repository: SQLiteCanonicalRepository | None = None


def repository() -> SQLiteCanonicalRepository:
    global _repository
    if _repository is None:
        _repository = SQLiteCanonicalRepository(get_settings().canonical_database_path)
    return _repository


def ingestion_service() -> IngestionService:
    settings = get_settings()
    runtime = build_runtime(settings)
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
    if required not in {value.strip() for value in permissions.split(",")}:
        raise HTTPException(status_code=403, detail="Insufficient permission")
    return OwnershipScope(tenant_id=tenant, project_id=project)


def document_scope(
    tenant: Annotated[str, Header(alias="X-Tenant-ID")],
    project: Annotated[str, Header(alias="X-Project-ID")],
    permissions: Annotated[str, Header(alias="X-Agent-Permissions")],
) -> OwnershipScope:
    return scope_and_permission(tenant, project, permissions, "documents:write")


def index_scope(
    tenant: Annotated[str, Header(alias="X-Tenant-ID")],
    project: Annotated[str, Header(alias="X-Project-ID")],
    permissions: Annotated[str, Header(alias="X-Agent-Permissions")],
) -> OwnershipScope:
    return scope_and_permission(tenant, project, permissions, "indexes:manage")


DocumentScope = Annotated[OwnershipScope, Depends(document_scope)]
IndexScope = Annotated[OwnershipScope, Depends(index_scope)]


@router.post("/documents/ingestions", status_code=status.HTTP_202_ACCEPTED)
def submit_ingestion(
    request: IngestionRequest,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    job = ingestion_service().submit(
        scope=scope,
        logical_source=request.logical_source,
        media_type=request.media_type,
        content=request.content_text.encode(),
        idempotency_key=idempotency_key,
    )
    return {"job_id": job.job_id, "stage": job.stage, "accepted": True}


@router.get("/ingestions/{job_id}")
def get_ingestion(
    job_id: str, scope: DocumentScope, _auth: InternalAuthDependency
) -> dict[str, object]:
    try:
        return repository().get_job(scope, job_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ingestion not found") from exc


@router.get("/documents/{document_id}/versions")
def versions(
    document_id: str, scope: DocumentScope, _auth: InternalAuthDependency
) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in repository().list_versions(scope, document_id)]


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    del idempotency_key
    return {"deleted": bool(repository().tombstone(scope, document_id))}


@router.post("/documents/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
def reprocess_document(
    document_id: str,
    scope: DocumentScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    versions = repository().list_versions(scope, document_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "accepted": True,
        "document_id": document_id,
        "idempotency_key_hash": __import__("hashlib")
        .sha256(idempotency_key.encode())
        .hexdigest()[:16],
    }


@router.get("/evidence/indexes/status")
def index_status(scope: IndexScope, _auth: InternalAuthDependency) -> dict[str, object]:
    del scope
    return {
        "vector_mode": get_settings().vector_mode,
        "manifests": [item.model_dump(mode="json") for item in repository().list_manifests()],
        "degraded": get_settings().vector_mode != "required",
    }


@router.post("/evidence/indexes/rebuild", status_code=status.HTTP_202_ACCEPTED)
def rebuild_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    return {
        "accepted": True,
        "operation": "rebuild",
        "scope": scope.model_dump(),
        "request_hash": __import__("hashlib").sha256(idempotency_key.encode()).hexdigest()[:16],
    }


@router.post("/evidence/indexes/rollback", status_code=status.HTTP_202_ACCEPTED)
def rollback_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    del idempotency_key
    return {"accepted": True, "operation": "rollback", "scope": scope.model_dump()}


@router.post("/evidence/indexes/reconcile", status_code=status.HTTP_202_ACCEPTED)
def reconcile_index(
    scope: IndexScope,
    _auth: InternalAuthDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
) -> dict[str, object]:
    del idempotency_key
    return {"accepted": True, "operation": "reconcile", "scope": scope.model_dump()}


@router.post("/evidence/search/diagnostics")
def diagnostics(
    request: DiagnosticRequest, scope: IndexScope, _auth: InternalAuthDependency
) -> dict[str, object]:
    result = get_retrieval_service().search(
        LiteratureSearchInput(
            query=request.query,
            top_k=10,
            retrieval_mode=get_settings().vector_mode,
            diagnostics=True,
        ),
        trusted_scope=scope,
    )
    return {
        "query_length": len(request.query),
        "filter_names": sorted(request.filters),
        "scope": scope.model_dump(),
        "mode": result.retrieval_mode,
        "degraded": result.degraded,
        "degraded_reason": result.degraded_reason
        or ("vector_disabled" if get_settings().vector_mode == "disabled" else None),
        "diagnostics": result.diagnostics,
        "evidence_ids": [hit.document_id for hit in result.hits],
    }
