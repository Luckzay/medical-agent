from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.models.run import (
    AnalysisResult,
    LLMStatus,
    ToolingMetadata,
    WorkflowMetadata,
    WorkflowStatus,
    WorkflowStep,
)
from app.models.tooling import (
    NormalizeHerbsOutput,
    ToolExecutionContext,
)
from app.services.analysis_service import AnalysisService
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS, build_tool_registry
from app.services.llm_proxy import LLMProxyClient
from app.services.tool_runtime import ToolRuntime

logger = logging.getLogger(__name__)
NodeHook = Callable[[str], None]


class WorkflowState(TypedDict):
    herbs: list[str]
    research_goal: NotRequired[str | None]
    normalized_herbs: NotRequired[list[str]]
    discovered: NotRequired[list[dict[str, object]]]
    compounds: NotRequired[list[dict[str, object]]]
    evidence: NotRequired[list[dict[str, object]]]
    claims: NotRequired[list[dict[str, object]]]
    retrieval_mode: NotRequired[str]
    retrieval_diagnostics: NotRequired[list[dict[str, object]]]
    proposal: NotRequired[dict[str, object]]
    proposal_review: NotRequired[dict[str, object]]
    unresolved_herbs: NotRequired[list[str]]
    online_failures: NotRequired[int]
    analysis_result: NotRequired[dict[str, object]]
    llm_summary: NotRequired[str | None]
    llm_status: NotRequired[str]
    steps: list[dict[str, object]]


class AnalysisWorkflow(Protocol):
    def invoke(
        self, run_id: str, herbs: list[str], research_goal: str | None = None
    ) -> AnalysisResult: ...

    def resume(self, run_id: str) -> AnalysisResult: ...

    def has_checkpoint(self, run_id: str) -> bool: ...

    def metadata(self, run_id: str, status: WorkflowStatus) -> WorkflowMetadata: ...

    def cancel(self, run_id: str) -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class LangGraphAnalysisWorkflow:
    """Simplified deterministic graph for medical agent analysis."""

    def __init__(
        self,
        analysis: AnalysisService,
        checkpointer: BaseCheckpointSaver[str] | None = None,
        node_hook: NodeHook | None = None,
        checkpoint_path: str | Path | None = None,
        runtime: ToolRuntime | None = None,
        llm: LLMProxyClient | None = None,
    ) -> None:
        self._analysis = analysis
        self._runtime = runtime or ToolRuntime(
            build_tool_registry(analysis), get_settings().database_path
        )
        self._llm = llm or LLMProxyClient(get_settings())
        self._owns_runtime = runtime is None
        self._node_hook = node_hook
        self._owned_connection: sqlite3.Connection | None = None
        if checkpointer is None:
            path = Path(checkpoint_path or get_settings().checkpoint_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            self._owned_connection = connection
            self._checkpointer: BaseCheckpointSaver[str] = SqliteSaver(connection)
            self._checkpoint_backend = "sqlite"
        else:
            self._checkpointer = checkpointer
            self._checkpoint_backend = (
                "in_memory" if isinstance(checkpointer, InMemorySaver) else "external"
            )
        builder = StateGraph(WorkflowState)
        builder.add_node("normalize", self._normalize)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "normalize")
        builder.add_edge("normalize", "finalize")
        builder.add_edge("finalize", END)
        self._graph = builder.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _config(run_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": run_id}}

    def _start(self, node: str) -> datetime:
        if self._node_hook is not None:
            self._node_hook(node)
        return datetime.now(UTC)

    @staticmethod
    def _step(node: str, started: datetime, detail: str) -> dict[str, object]:
        return cast(
            dict[str, object],
            WorkflowStep(
                node=node,
                status="completed",
                started_at=started,
                completed_at=datetime.now(UTC),
                detail=detail,
            ).model_dump(mode="json"),
        )

    @staticmethod
    def _run_id(config: RunnableConfig) -> str:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str):
            raise RuntimeError("LangGraph thread_id is missing")
        return thread_id

    def _tool_context(self, config: RunnableConfig, node: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            run_id=self._run_id(config), node=node, permissions=INTERNAL_TOOL_PERMISSIONS
        )

    def _normalize(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("normalize")
        output = NormalizeHerbsOutput.model_validate(
            self._runtime.execute(
                "normalize_herbs",
                {"herbs": state["herbs"]},
                self._tool_context(config, "normalize"),
            )
        )
        normalized = output.normalized_herbs
        return {
            "normalized_herbs": normalized,
            "steps": [
                *state["steps"],
                self._step("normalize", started, f"标准化 {len(normalized)} 味药材"),
            ],
        }

    def _finalize(self, state: WorkflowState, config: RunnableConfig) -> dict[str, object]:
        started = self._start("finalize")
        settings = get_settings()

        llm_status = LLMStatus.DISABLED
        llm_summary = None

        if settings.llm_mode != "disabled":
            try:
                llm_summary = self._llm.chat(
                    system_prompt="You are a medical assistant.",
                    user_prompt=(
                        "Summarize the analysis for herbs: "
                        f"{state.get('normalized_herbs', [])}"
                    ),
                )
                llm_status = LLMStatus.GENERATED
            except Exception as exc:
                if settings.llm_mode == "required":
                    raise
                llm_status = LLMStatus.DEGRADED
                logger.warning(f"LLM enhancement failed: {exc}")

        result = self._analysis.finalize(
            state.get("normalized_herbs", []),
            [],  # compounds
            [],  # evidence
            [],  # unresolved
            0,   # online failures
            llm_summary=llm_summary,
            llm_status=llm_status,
        )

        steps_data = [
            *state["steps"],
            self._step("finalize", started, "汇总分析结果与能力状态"),
        ]
        thread_id = self._run_id(config)
        audits = self._runtime.audits_for_run(thread_id)
        result.workflow = WorkflowMetadata(
            thread_id=thread_id,
            checkpoint_backend=self._checkpoint_backend,
            status=WorkflowStatus.COMPLETED,
            steps=[WorkflowStep.model_validate(item) for item in steps_data],
            tooling=ToolingMetadata(
                skills=[],
                audit_ids=[audit.audit_id for audit in audits],
            ),
        )
        return {"analysis_result": result.model_dump(mode="json"), "steps": steps_data}

    def invoke(
        self, run_id: str, herbs: list[str], research_goal: str | None = None
    ) -> AnalysisResult:
        output = self._graph.invoke(
            WorkflowState(herbs=herbs, research_goal=research_goal, steps=[]),
            config=self._config(run_id),
        )
        return AnalysisResult.model_validate(output["analysis_result"])

    def resume(self, run_id: str) -> AnalysisResult:
        output = self._graph.invoke(None, config=self._config(run_id))
        return AnalysisResult.model_validate(output["analysis_result"])

    def has_checkpoint(self, run_id: str) -> bool:
        return self._checkpointer.get_tuple(self._config(run_id)) is not None

    def metadata(self, run_id: str, status: WorkflowStatus) -> WorkflowMetadata:
        snapshot = self._graph.get_state(self._config(run_id))
        values = cast(WorkflowState, snapshot.values)
        steps = [WorkflowStep.model_validate(item) for item in values.get("steps", [])]
        if status is WorkflowStatus.FAILED and snapshot.next:
            now = datetime.now(UTC)
            steps.append(
                WorkflowStep(
                    node=snapshot.next[0],
                    status="failed",
                    started_at=now,
                    completed_at=now,
                    detail="节点执行异常；已保留前序 checkpoint，可从此节点恢复",
                )
            )
        return WorkflowMetadata(
            thread_id=run_id,
            checkpoint_backend=self._checkpoint_backend,
            status=status,
            steps=steps,
        )

    def cancel(self, run_id: str) -> None:
        self.metadata(run_id, WorkflowStatus.CANCELLED)

    def clear(self) -> None:
        thread_ids = {
            str(item.config["configurable"]["thread_id"]) for item in self._checkpointer.list(None)
        }
        for thread_id in thread_ids:
            self._checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        if self._owned_connection is not None:
            self._owned_connection.close()
            self._owned_connection = None
        if self._owns_runtime:
            self._runtime.close()
