from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from app.models.proposal import ExperimentProposal
from app.models.run import ClaimEvidence, CompoundResult, Evidence
from app.models.tooling import (
    DescribedCompound,
    DiscoveredCompoundModel,
    SearchLiteratureInput,
    ToolExecutionContext,
)
from app.services.builtin_tools import MCP_TOOL_PERMISSIONS
from app.services.tool_runtime import ToolRuntime


def _context(tool_name: str, run_id: str | None) -> ToolExecutionContext:
    identifier = run_id.strip() if run_id is not None else uuid4().hex
    if not identifier:
        identifier = uuid4().hex
    return ToolExecutionContext(
        run_id=f"mcp_{identifier}", node=f"mcp:{tool_name}", permissions=MCP_TOOL_PERMISSIONS
    )


def build_mcp_server(runtime: ToolRuntime) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer(
        name="medical-agent-tool-runtime",
        description="中药复方确定性分析工具运行时",
        version="0.7.0",
    )

    @server.tool(name="normalize_herbs", description="标准化、去重中药材名称。")
    def normalize_herbs(herbs: list[str], run_id: str | None = None) -> dict[str, Any]:
        output = runtime.execute(
            "normalize_herbs", {"herbs": herbs}, _context("normalize_herbs", run_id)
        )
        return output.model_dump(mode="json")

    @server.tool(name="discover_compounds", description="发现药材成分并返回完整证据状态。")
    def discover_compounds(
        normalized_herbs: list[str], run_id: str | None = None
    ) -> dict[str, Any]:
        output = runtime.execute(
            "discover_compounds",
            {"normalized_herbs": normalized_herbs},
            _context("discover_compounds", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="calculate_descriptors", description="批量计算分子描述符。")
    def calculate_descriptors(
        compounds: list[DiscoveredCompoundModel], run_id: str | None = None
    ) -> dict[str, Any]:
        output = runtime.execute(
            "calculate_descriptors",
            {"compounds": [item.model_dump(mode="json") for item in compounds]},
            _context("calculate_descriptors", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="score_supramolecular_candidate", description="批量评分超分子候选。")
    def score_supramolecular_candidate(
        compounds: list[DescribedCompound], run_id: str | None = None
    ) -> dict[str, Any]:
        output = runtime.execute(
            "score_supramolecular_candidate",
            {"compounds": [item.model_dump(mode="json") for item in compounds]},
            _context("score_supramolecular_candidate", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="search_literature", description="离线混合检索超分子中药文献证据。")
    def search_literature(
        query: str | None = None,
        herbs: list[str] | None = None,
        compounds: list[str] | None = None,
        smiles: list[str] | None = None,
        top_k: int = 10,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        request = SearchLiteratureInput(
            query=query,
            herbs=herbs or [],
            compounds=compounds or [],
            smiles=smiles or [],
            top_k=top_k,
        )
        output = runtime.execute(
            "search_literature",
            request,
            _context("search_literature", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="generate_experiment_proposal", description="生成证据约束的确定性实验方案。")
    def generate_experiment_proposal_tool(
        compounds: list[CompoundResult],
        claims: list[ClaimEvidence],
        evidence: list[Evidence],
        max_conditions: int = 12,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        output = runtime.execute(
            "generate_experiment_proposal",
            {
                "compounds": [item.model_dump(mode="json") for item in compounds],
                "claims": [item.model_dump(mode="json") for item in claims],
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "max_conditions": max_conditions,
            },
            _context("generate_experiment_proposal", run_id),
        )
        return output.model_dump(mode="json")

    @server.tool(name="review_experiment_proposal", description="独立审查实验方案与证据引用。")
    def review_experiment_proposal_tool(
        proposal: ExperimentProposal,
        available_evidence_ids: list[str],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        output = runtime.execute(
            "review_experiment_proposal",
            {
                "proposal": proposal.model_dump(mode="json"),
                "available_evidence_ids": available_evidence_ids,
            },
            _context("review_experiment_proposal", run_id),
        )
        return output.model_dump(mode="json")

    return server


class RestartableMCPApplication:
    """Rebuilds the v2 one-shot session manager for every parent ASGI lifespan."""

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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._app
        if app is None:
            raise RuntimeError("MCP application lifespan is not running")
        await app(scope, receive, send)
