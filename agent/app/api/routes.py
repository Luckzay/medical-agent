from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.models.chat import ChatTurnCreate, ChatTurnResponse
from app.models.run import HealthResponse, RunCreate, RunResponse
from app.models.tooling import SkillResponse, ToolMetadataResponse
from app.services.agent.chat.service import (
    ChatTurnNotFoundError,
    ChatTurnService,
    DuplicateChatTurnError,
)
from app.services.agent.run.service import (
    DuplicateRunError,
    RunConflictError,
    RunNotFoundError,
    RunService,
)
from app.services.runtime import run_service
from app.services.tools.runtime import ToolRuntime

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

ERROR_RESPONSES = {
    401: {"description": "未授权：无效或缺失的 Agent Token"},
    404: {"description": "未找到：请求的资源不存在"},
    409: {"description": "冲突：资源已存在或状态冲突"},
}


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Service"],
    summary="服务健康检查",
    description="返回服务的健康状态、名称和版本号。",
)
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
    tags=["Chat"],
    summary="创建对话回合（毒理活跃）",
    description="""
发起一个新的智能体对话回合。该接口当前硬编码为**中药毒理专家**，将自动调用毒理知识库检索工具。
采用异步处理模式，返回 202 Accepted。客户端应后续通过 GET 接口轮询处理事件。
""",
    responses={
        401: ERROR_RESPONSES[401],
        409: ERROR_RESPONSES[409],
    },
)
def create_chat_turn(
    request: ChatTurnCreate,
    service: ChatServiceDependency,
    _authenticated: InternalAuthDependency,
) -> ChatTurnResponse:
    """创建并启动一个异步聊天回合任务。"""
    try:
        return service.create(request)
    except DuplicateChatTurnError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chat turn '{request.turn_id}' already exists",
        ) from exc


@router.get(
    "/internal/v1/chat/turns/{turn_id}",
    response_model=ChatTurnResponse,
    tags=["Chat"],
    summary="获取对话回合详情",
    description="查询特定对话回合的状态、事件流和最终回答。",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
    },
)
def get_chat_turn(
    turn_id: str,
    service: ChatServiceDependency,
    _authenticated: InternalAuthDependency,
) -> ChatTurnResponse:
    """根据 turn_id 获取聊天回合的最新状态 and 事件。"""
    try:
        return service.get(turn_id)
    except ChatTurnNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat turn '{turn_id}' not found",
        ) from exc


@router.get(
    "/internal/v1/tools",
    response_model=list[ToolMetadataResponse],
    tags=["Metadata"],
    summary="列出可用工具",
    description="获取当前 Agent 服务注册的所有只读与计算工具的元数据及输入输出 Schema。",
    responses={401: ERROR_RESPONSES[401]},
)
def list_tools(
    runtime: ToolRuntimeDependency, _authenticated: InternalAuthDependency
) -> list[dict[str, object]]:
    return runtime.registry.list_tools()


@router.get(
    "/internal/v1/skills",
    response_model=list[SkillResponse],
    tags=["Metadata"],
    summary="列出可用技能",
    description="获取当前加载的技能包定义，包含关联的工具列表。",
    responses={401: ERROR_RESPONSES[401]},
)
def list_skills(
    runtime: ToolRuntimeDependency, _authenticated: InternalAuthDependency
) -> list[dict[str, object]]:
    return runtime.registry.list_skills()


@router.get(
    "/internal/v1/runs/{run_id}/tool-audits",
    tags=["Runs"],
    summary="查询运行工具审计日志",
    description="获取特定分析运行任务中产生的所有工具调用详细审计日志，包括耗时和状态。",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
    },
)
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
    tags=["Runs"],
    summary="创建分析运行任务",
    description="启动一个新的中药成分分析任务。该任务为长耗时任务，建议通过 ID 追踪进度。",
    responses={
        401: ERROR_RESPONSES[401],
        409: ERROR_RESPONSES[409],
    },
)
def create_run(
    request: RunCreate,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    """初始化并运行一个新的分析任务。"""
    try:
        return service.create(request)
    except DuplicateRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{request.run_id}' already exists",
        ) from exc


@router.post(
    "/internal/v1/runs/{run_id}/resume",
    response_model=RunResponse,
    tags=["Runs"],
    summary="恢复运行任务",
    description="对于处于挂起或特定中断状态的任务，尝试重新启动执行。",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
def resume_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    """恢复一个先前中断的运行任务。"""
    try:
        return service.resume(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc
    except RunConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/internal/v1/runs/{run_id}",
    response_model=RunResponse,
    tags=["Runs"],
    summary="获取运行任务详情",
    description="查询分析任务的实时进度、工作流步骤及最终分析结果。",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
    },
)
def get_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    """获取运行任务的完整状态。"""
    try:
        return service.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc


@router.delete(
    "/internal/v1/runs/{run_id}",
    response_model=RunResponse,
    tags=["Runs"],
    summary="取消运行任务",
    description="尝试停止正在执行的分析任务并标记为已取消。",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
    },
)
def cancel_run(
    run_id: str,
    service: RunServiceDependency,
    _authenticated: InternalAuthDependency,
) -> RunResponse:
    """取消指定的运行任务。"""
    try:
        return service.cancel(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        ) from exc
