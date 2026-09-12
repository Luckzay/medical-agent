from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.models.chat import ChatTurnCreate, ChatTurnResponse
from app.models.run import HealthResponse, RunCreate, RunResponse
from app.services.chat_service import (
    ChatTurnNotFoundError,
    ChatTurnService,
    DuplicateChatTurnError,
)
from app.services.run_service import (
    DuplicateRunError,
    RunConflictError,
    RunNotFoundError,
    RunService,
    run_service,
)
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
