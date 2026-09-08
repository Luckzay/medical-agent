from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from secrets import compare_digest

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.api.management import router as management_router
from app.api.routes import chat_service, router
from app.core.config import get_settings
from app.services.mcp_server import RestartableMCPApplication
from app.services.run_service import run_service

settings = get_settings()
mcp_application = RestartableMCPApplication(run_service.runtime)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with mcp_application.lifespan():
        run_service.recover_running_tasks()
        chat_service.recover_pending_tasks()
        try:
            yield
        finally:
            # Both services are restartable for repeated TestClient lifespans.
            chat_service.close()
            run_service.shutdown(wait=True)
            run_service.runtime.close()
            run_service.evidence_store.close()


app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    lifespan=lifespan,
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
