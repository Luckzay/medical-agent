"""Application composition root.

This module is the only service module allowed to assemble dependencies across the
agent, knowledge, tools, and infrastructure layers.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.services.agent.analysis import AnalysisService
from app.services.agent.run.service import RunService
from app.services.knowledge.storage.factory import get_vector_runtime
from app.services.tools.builtin import build_tool_registry
from app.services.tools.runtime import ToolRuntime


def build_run_service(settings: Settings | None = None) -> RunService:
    configured = settings or get_settings()
    analysis = AnalysisService(configured)
    tool_runtime = ToolRuntime(build_tool_registry(analysis))
    return RunService(
        analysis_service=analysis,
        runtime=tool_runtime,
        settings=configured,
    )


def warm_vector_runtime() -> None:
    get_vector_runtime().embedding.embed_query("中药毒理知识检索预热")


run_service = build_run_service()
