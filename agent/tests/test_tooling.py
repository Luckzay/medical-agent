from __future__ import annotations

from threading import Event
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.models.tooling import (
    NormalizeHerbsInput,
    RetryPolicy,
    SkillDefinition,
    ToolDefinition,
    ToolExecutionContext,
)
from app.services.analysis_service import AnalysisService
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS, build_tool_registry
from app.services.tool_registry import (
    DuplicateToolError,
    ToolRegistry,
    UnknownToolReferenceError,
)
from app.services.tool_runtime import (
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolPermissionError,
    ToolRuntime,
    ToolTimeoutError,
)
from app.services.workflow import LangGraphAnalysisWorkflow


class ValueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: int


class ValueOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: int


def definition(handler: Any, **kwargs: Any) -> ToolDefinition[ValueInput, ValueOutput]:
    return ToolDefinition[ValueInput, ValueOutput](
        name="test_tool",
        version="1.0.0",
        description="test",
        input_model=ValueInput,
        output_model=ValueOutput,
        required_permissions=frozenset({"test:execute"}),
        handler=handler,
        **kwargs,
    )


def context() -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run-tool-test", node="test", permissions=frozenset({"test:execute"})
    )


def test_registry_rejects_conflicts_and_unknown_skill_tools() -> None:
    registry = ToolRegistry()
    item = definition(lambda request: ValueOutput(value=request.value))
    registry.register_tool(item)
    with pytest.raises(DuplicateToolError):
        registry.register_tool(item)
    with pytest.raises(UnknownToolReferenceError):
        registry.register_skill(
            SkillDefinition(
                name="broken-skill",
                version="1",
                description="broken",
                tool_names=("missing",),
                context_policy={},
            )
        )


def test_runtime_audits_permission_and_validation_failures(tmp_path: Any) -> None:
    registry = ToolRegistry()
    registry.register_tool(definition(lambda request: ValueOutput(value=request.value)))
    runtime = ToolRuntime(registry, tmp_path / "audit.db")
    denied = context().model_copy(update={"permissions": frozenset()})
    with pytest.raises(ToolPermissionError):
        runtime.execute("test_tool", {"value": 1}, denied)
    with pytest.raises(ToolInputValidationError):
        runtime.execute("test_tool", {"value": "secret-payload"}, context())
    audits = runtime.audits_for_run("run-tool-test")
    assert [audit.status for audit in audits] == ["permission_denied", "input_validation_failed"]
    assert all("secret-payload" not in (audit.error_message or "") for audit in audits)
    runtime.close()


def test_runtime_retries_and_validates_output(tmp_path: Any) -> None:
    attempts = 0

    def flaky(request: ValueInput) -> ValueOutput:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")
        return ValueOutput(value=request.value)

    registry = ToolRegistry()
    registry.register_tool(definition(flaky, retry_policy=RetryPolicy(max_retries=1)))
    runtime = ToolRuntime(registry, tmp_path / "retry.db")
    assert runtime.execute("test_tool", {"value": 7}, context()) == ValueOutput(value=7)
    assert runtime.audits_for_run("run-tool-test")[0].attempts == 2
    runtime.close()

    invalid_registry = ToolRegistry()
    invalid_registry.register_tool(definition(lambda _request: {"value": "bad"}))
    invalid_runtime = ToolRuntime(invalid_registry, tmp_path / "invalid.db")
    with pytest.raises(ToolOutputValidationError):
        invalid_runtime.execute("test_tool", {"value": 1}, context())
    assert invalid_runtime.audits_for_run("run-tool-test")[0].status == "output_validation_failed"
    invalid_runtime.close()


def test_runtime_timeout_is_audited_without_sleep(tmp_path: Any) -> None:
    release = Event()
    entered = Event()

    def blocking(request: ValueInput) -> ValueOutput:
        entered.set()
        release.wait()
        return ValueOutput(value=request.value)

    registry = ToolRegistry()
    registry.register_tool(definition(blocking, timeout_seconds=0.01))
    runtime = ToolRuntime(registry, tmp_path / "timeout.db")
    try:
        with pytest.raises(ToolTimeoutError):
            runtime.execute("test_tool", {"value": 1}, context())
        assert entered.is_set()
        assert runtime.audits_for_run("run-tool-test")[0].status == "timeout"
    finally:
        release.set()
        runtime.close()


def test_builtin_tools_and_workflow_use_runtime_in_order(tmp_path: Any) -> None:
    settings = Settings(
        internal_token="test-only-agent-token",
        offline_mode=True,
        database_path=tmp_path / "runs.db",
        checkpoint_path=tmp_path / "checkpoints.db",
    )
    analysis = AnalysisService(settings)
    registry = build_tool_registry(analysis)
    runtime = ToolRuntime(registry, settings.database_path)

    normalized = runtime.execute(
        "normalize_herbs",
        NormalizeHerbsInput(herbs=[" 黃耆 ", "当归"]),
        ToolExecutionContext(
            run_id="builtins", node="normalize", permissions=INTERNAL_TOOL_PERMISSIONS
        ),
    )
    discovered = runtime.execute(
        "discover_compounds",
        {"normalized_herbs": normalized.model_dump()["normalized_herbs"]},
        ToolExecutionContext(
            run_id="builtins", node="discover", permissions=INTERNAL_TOOL_PERMISSIONS
        ),
    )
    described = runtime.execute(
        "calculate_descriptors",
        {"compounds": discovered.model_dump(mode="json")["compounds"]},
        ToolExecutionContext(
            run_id="builtins", node="chemistry", permissions=INTERNAL_TOOL_PERMISSIONS
        ),
    )
    scored = runtime.execute(
        "score_supramolecular_candidate",
        {"compounds": described.model_dump(mode="json")["compounds"]},
        ToolExecutionContext(
            run_id="builtins", node="chemistry", permissions=INTERNAL_TOOL_PERMISSIONS
        ),
    )
    assert len(scored.model_dump()["compounds"]) == 2

    workflow = LangGraphAnalysisWorkflow(analysis, checkpointer=InMemorySaver(), runtime=runtime)
    result = workflow.invoke("workflow-tools", ["黄芪"])
    audits = runtime.audits_for_run("workflow-tools")
    assert [audit.tool_name for audit in audits] == [
        "normalize_herbs",
        "discover_compounds",
        "calculate_descriptors",
        "score_supramolecular_candidate",
        "search_literature",
        "generate_experiment_proposal",
        "review_experiment_proposal",
    ]
    assert result.workflow is not None and result.workflow.tooling is not None
    assert result.workflow.tooling.audit_ids == [audit.audit_id for audit in audits]
    workflow.close()
    runtime.close()
