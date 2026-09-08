from functools import lru_cache
from secrets import compare_digest
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.models.chat import ChatTurnCreate, ChatTurnResponse
from app.models.evidence import DataQualityReport
from app.models.proposal import ProposalResponse
from app.models.run import HealthResponse, RunCreate, RunResponse, RunStatus
from app.models.supramolecular import SupramolecularSearchRequest, SupramolecularSearchResponse
from app.models.tooling import SearchLiteratureInput, SearchLiteratureOutput, ToolExecutionContext
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS
from app.services.chat_service import (
    ChatTurnNotFoundError,
    ChatTurnService,
    DuplicateChatTurnError,
)
from app.services.embeddings import (
    DeterministicTestEmbedding,
    EmbeddingProvider,
    LazySentenceTransformerEmbedding,
)
from app.services.run_service import (
    DuplicateRunError,
    RunConflictError,
    RunNotFoundError,
    RunService,
    run_service,
)
from app.services.supramolecular_retrieval import SupramolecularSearchService
from app.services.tool_runtime import ToolRuntime

router = APIRouter()
agent_token_header = APIKeyHeader(name="X-Agent-Token", auto_error=False)
chat_service = ChatTurnService(run_service.runtime)


def get_run_service() -> RunService:
    return run_service


def verify_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Security(agent_token_header)],
) -> bool:
    if token is None or not compare_digest(token, settings.internal_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent token",
        )
    return True


SettingsDependency = Annotated[Settings, Depends(get_settings)]
RunServiceDependency = Annotated[RunService, Depends(get_run_service)]
InternalAuthDependency = Annotated[bool, Depends(verify_internal_token)]


@lru_cache
def get_supramolecular_search_service() -> SupramolecularSearchService:
    settings = get_settings()
    embedding: EmbeddingProvider
    if settings.embedding_provider == "deterministic_test":
        embedding = DeterministicTestEmbedding(
            settings.embedding_dimension, normalize=settings.embedding_normalize
        )
    else:
        embedding = LazySentenceTransformerEmbedding(
            settings.embedding_model,
            settings.embedding_revision,
            settings.embedding_dimension,
            normalize=settings.embedding_normalize,
            batch_size=settings.embedding_batch_size,
            retries=settings.embedding_retries,
            timeout_seconds=settings.embedding_timeout_seconds,
            device=settings.embedding_device,
            max_seq_length=settings.embedding_max_seq_length,
        )
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=max(1, int(settings.qdrant_timeout_seconds)),
    )
    # 当前工程没有通用 LLM provider；不构造隐式网络依赖，摘要能力保持安全可选。
    return SupramolecularSearchService(
        client,
        embedding,
        settings.supramolecular_collection,
        candidate_multiplier=settings.supramolecular_candidate_multiplier,
        rrf_k=settings.fusion_rrf_k,
    )


SupramolecularSearchDependency = Annotated[
    SupramolecularSearchService, Depends(get_supramolecular_search_service)
]


@router.post("/supramolecular/search", response_model=SupramolecularSearchResponse)
def search_supramolecular(
    request: SupramolecularSearchRequest,
    service: SupramolecularSearchDependency,
) -> SupramolecularSearchResponse:
    try:
        return service.search(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supramolecular search is temporarily unavailable",
        ) from exc


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        version=settings.service_version,
    )


def get_tool_runtime(service: RunServiceDependency) -> ToolRuntime:
    return service.runtime


ToolRuntimeDependency = Annotated[ToolRuntime, Depends(get_tool_runtime)]


def get_chat_service() -> ChatTurnService:
    return chat_service


ChatServiceDependency = Annotated[ChatTurnService, Depends(get_chat_service)]


@router.post(
    "/internal/v1/chat/turns",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_chat_turn(
    request: ChatTurnCreate,
    service: ChatServiceDependency,
    _authenticated: InternalAuthDependency,
) -> ChatTurnResponse:
    try:
        return service.create(request)
    except DuplicateChatTurnError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chat turn '{request.turn_id}' already exists",
        ) from exc


@router.get("/internal/v1/chat/turns/{turn_id}", response_model=ChatTurnResponse)
def get_chat_turn(
    turn_id: str,
    service: ChatServiceDependency,
    _authenticated: InternalAuthDependency,
) -> ChatTurnResponse:
    try:
        return service.get(turn_id)
    except ChatTurnNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat turn '{turn_id}' not found",
        ) from exc


@router.get("/internal/v1/evidence/quality", response_model=DataQualityReport)
def evidence_quality(
    service: RunServiceDependency, _authenticated: InternalAuthDependency
) -> DataQualityReport:
    return service.evidence_store.quality_report()


@router.post("/internal/v1/evidence/search", response_model=SearchLiteratureOutput)
def search_evidence(
    request: SearchLiteratureInput,
    runtime: ToolRuntimeDependency,
    _authenticated: InternalAuthDependency,
) -> SearchLiteratureOutput:
    output = runtime.execute(
        "search_literature",
        request,
        ToolExecutionContext(
            run_id=f"api_evidence_{uuid4().hex}",
            node="api:evidence",
            permissions=INTERNAL_TOOL_PERMISSIONS,
        ),
    )
    return SearchLiteratureOutput.model_validate(output)


@router.get("/internal/v1/tools")
def list_tools(
    runtime: ToolRuntimeDependency, _authenticated: InternalAuthDependency
) -> list[dict[str, object]]:
    return runtime.registry.list_tools()


@router.get("/internal/v1/skills")
def list_skills(
    runtime: ToolRuntimeDependency, _authenticated: InternalAuthDependency
) -> list[dict[str, object]]:
    return runtime.registry.list_skills()


@router.get("/internal/v1/runs/{run_id}/tool-audits")
def list_tool_audits(
    run_id: str,
    runtime: ToolRuntimeDependency,
    _authenticated: InternalAuthDependency,
) -> list[dict[str, object]]:
    return [audit.model_dump(mode="json") for audit in runtime.audits_for_run(run_id)]


@router.post(
    "/internal/v1/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    request: RunCreate,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    try:
        return service.create(request)
    except DuplicateRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{request.run_id}' already exists",
        ) from exc


@router.post("/internal/v1/runs/{run_id}/resume", response_model=RunResponse)
def resume_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    try:
        return service.resume(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc
    except RunConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/internal/v1/runs/{run_id}/proposal", response_model=ProposalResponse)
def get_run_proposal(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> ProposalResponse:
    try:
        run = service.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc
    result = run.analysis_result
    if (
        run.status is not RunStatus.COMPLETED
        or result is None
        or result.proposal is None
        or result.proposal_review is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' proposal is not available",
        )
    return ProposalResponse(proposal=result.proposal, review=result.proposal_review)


@router.get("/internal/v1/runs/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    try:
        return service.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc


@router.delete("/internal/v1/runs/{run_id}", response_model=RunResponse)
def cancel_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    try:
        return service.cancel(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc
