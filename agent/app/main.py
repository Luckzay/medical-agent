import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from secrets import compare_digest

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.api.management import router as management_router
from app.api.routes import chat_service, router
from app.core.config import get_settings
from app.services.runtime import run_service, warm_vector_runtime
from app.services.tools.mcp import RestartableMCPApplication

logger = logging.getLogger(__name__)

settings = get_settings()
mcp_application = RestartableMCPApplication(run_service.runtime)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with mcp_application.lifespan():
        run_service.recover_running_tasks()
        chat_service.recover_pending_tasks()
        if settings.vector_mode != "disabled":
            try:
                await asyncio.to_thread(warm_vector_runtime)
            except Exception:
                if settings.vector_mode == "required":
                    raise
                logger.exception("Vector runtime warm-up failed; continuing in optional mode")
        try:
            yield
        finally:
            # Both services are restartable for repeated TestClient lifespans.
            chat_service.close()
            run_service.shutdown(wait=True)
            run_service.runtime.close()


app = FastAPI(
    title="Medical Agent Service",
    description="""
中药科研辅助智能体服务。
当前版本集成了**活跃的中药毒理专家**能力，支持基于知识库的异步对话、成分分析以及知识库入库与索引管理。
注意：**超分子文献检索与诊断功能已暂时下线**。
除 `/health` 接口外，所有 `/internal/v1/*` 接口均需通过 `X-Agent-Token` 进行鉴权。
""",
    version=settings.service_version,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Chat", "description": "智能体异步对话接口"},
        {"name": "Runs", "description": "长耗时分析任务管理"},
        {"name": "Ingestion", "description": "知识库文档异步入库"},
        {"name": "Documents", "description": "规范化文档与版本管理"},
        {"name": "Index Management", "description": "向量索引底交代号与同步管理"},
        {"name": "Metadata", "description": "工具与技能元数据查询"},
        {"name": "Service", "description": "服务基础功能"},
    ],
)
app.include_router(router)
app.include_router(management_router)
app.mount("/mcp", mcp_application, name="mcp")


@app.middleware("http")
async def authenticate_mcp_path(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path == "/mcp" or request.url.path.startswith("/mcp/"):
        token = request.headers.get("X-Agent-Token")
        if token is None or not compare_digest(token, settings.internal_token):
            return JSONResponse(
                status_code=401, content={"detail": "Invalid or missing agent token"}
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed"},
    )
