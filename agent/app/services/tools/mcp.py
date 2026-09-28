from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.models.tooling import (
    NormalizeHerbsInput,
    SearchMedicalKnowledgeInput,
    ToolExecutionContext,
)
from app.services.tools.builtin import MCP_TOOL_PERMISSIONS
from app.services.tools.runtime import ToolRuntime

logger = logging.getLogger(__name__)


def _context(tool_name: str, run_id: str | None) -> ToolExecutionContext:
    identifier = run_id.strip() if run_id is not None else uuid4().hex
    if not identifier:
        identifier = uuid4().hex
    return ToolExecutionContext(
        run_id=f"mcp_{identifier}", node=f"mcp:{tool_name}", permissions=MCP_TOOL_PERMISSIONS
    )


def build_mcp_server(runtime: ToolRuntime) -> MCPServer[None]:
    server = MCPServer(
        name="medical-agent-mcp",
        description="Medical Agent MCP Server",
        version="1.0.0",
    )

    @server.tool(name="normalize_herbs", description="标准化中药材名称。")
    def normalize_herbs_tool(herbs: list[str], run_id: str | None = None) -> dict[str, Any]:
        output = runtime.execute(
            "normalize_herbs",
            NormalizeHerbsInput(herbs=herbs).model_dump(mode="json"),
            _context("normalize_herbs", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="search_medical_knowledge", description="检索业务数据库医学知识。")
    def search_medical_knowledge_tool(
        query: str, limit: int = 10, run_id: str | None = None
    ) -> dict[str, Any]:
        output = runtime.execute(
            "search_medical_knowledge",
            SearchMedicalKnowledgeInput(query=query, limit=limit).model_dump(mode="json"),
            _context("search_medical_knowledge", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="search_toxicology_knowledge", description="检索中药毒理索引。")
    def search_toxicology_knowledge_tool(
        query: str, limit: int = 10, run_id: str | None = None
    ) -> dict[str, Any]:
        output = runtime.execute(
            "search_toxicology_knowledge",
            SearchMedicalKnowledgeInput(query=query, limit=limit).model_dump(mode="json"),
            _context("search_toxicology_knowledge", run_id),
        )
        return output.model_dump(mode="json")

    return server


class RestartableMCPApplication:
    """Rebuilds the one-shot session manager for every parent ASGI lifespan."""

    def __init__(self, runtime: ToolRuntime) -> None:
        self._runtime = runtime
        self._app: Any | None = None

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        server = build_mcp_server(self._runtime)
        app = server.streamable_http_app(
            streamable_http_path="/",
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[
                    "127.0.0.1",
                    "127.0.0.1:*",
                    "localhost",
                    "localhost:*",
                    "agent",
                    "agent:*",
                    "testserver",
                    "testserver:*",
                ],
                allowed_origins=[
                    "http://127.0.0.1",
                    "http://localhost",
                    "http://testserver",
                ],
            ),
        )
        self._app = app
        try:
            async with app.router.lifespan_context(app):
                yield
        finally:
            self._app = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        app = self._app
        if app is None:
            raise RuntimeError("MCP application lifespan is not running")
        await app(scope, receive, send)
