from collections.abc import Iterator
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routes import get_run_service
from app.core.config import Settings
from app.main import app
from app.models.run import MolecularDescriptors, RunCreate, RunStatus
from app.services.analysis_service import AnalysisService
from app.services.run_repository import SQLiteRunRepository
from app.services.run_service import RunConflictError, RunService
from app.services.workflow import LangGraphAnalysisWorkflow


class UnavailableDescriptors:
    available = False

    def calculate(self, smiles: str) -> MolecularDescriptors:
        return MolecularDescriptors()


class NodeController:
    def __init__(self, *, fail_chemistry_once: bool = False, block_normalize: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_chemistry_once = fail_chemistry_once
        self.block_normalize = block_normalize
        self.entered = Event()
        self.release = Event()

    def __call__(self, node: str) -> None:
        self.calls.append(node)
        if node == "normalize" and self.block_normalize:
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise TimeoutError("test did not release normalize node")
        if node == "chemistry" and self.fail_chemistry_once:
            self.fail_chemistry_once = False
            raise RuntimeError("injected chemistry failure")


def settings(tmp_path: Path) -> Settings:
    return Settings(
        internal_token="test-only-agent-token",
        offline_mode=True,
        database_path=tmp_path / "runs.db",
        checkpoint_path=tmp_path / "checkpoints.db",
    )


def make_service(
    tmp_path: Path,
    hook: NodeController | None = None,
    *,
    durable_checkpoints: bool = False,
) -> RunService:
    configured = settings(tmp_path)
    analysis = AnalysisService(configured, descriptors=UnavailableDescriptors())
    workflow = LangGraphAnalysisWorkflow(
        analysis,
        checkpointer=None if durable_checkpoints else InMemorySaver(),
        node_hook=hook,
        checkpoint_path=configured.checkpoint_path,
    )
    return RunService(
        analysis_service=analysis,
        workflow=workflow,
        repository=SQLiteRunRepository(configured.database_path),
        settings=configured,
    )


def request(run_id: str = "workflow-run") -> RunCreate:
    return RunCreate(
        run_id=run_id,
        user_id=1001,
        trace_id="trace-workflow",
        herbs=["黃耆", "当归"],
        research_goal=None,
    )


def test_graph_runs_in_background_and_serializes_trace(tmp_path: Path) -> None:
    hook = NodeController()
    service = make_service(tmp_path, hook)
    created = service.create(request())

    assert created.status is RunStatus.RUNNING
    assert service.wait_for_idle(timeout=5)
    run = service.get("workflow-run")
    assert run.status is RunStatus.COMPLETED
    assert hook.calls == [
        "normalize",
        "discover",
        "chemistry",
        "evidence",
        "proposal",
        "review",
        "finalize",
    ]
    assert run.workflow is not None
    assert run.workflow.thread_id == "workflow-run"
    assert run.workflow.checkpoint_backend == "in_memory"
    assert run.analysis_result is not None
    assert run.analysis_result.workflow == run.workflow
    run.model_dump(mode="json")
    service.close()


def test_failure_checkpoint_and_fast_resume(tmp_path: Path) -> None:
    hook = NodeController(fail_chemistry_once=True)
    service = make_service(tmp_path, hook)

    assert service.create(request()).status is RunStatus.RUNNING
    assert service.wait_for_idle(timeout=5)
    failed = service.get("workflow-run")
    assert failed.status is RunStatus.FAILED
    assert failed.error_message == "injected chemistry failure"

    resumed = service.resume("workflow-run")
    assert resumed.status is RunStatus.RUNNING
    assert service.wait_for_idle(timeout=5)
    completed = service.get("workflow-run")
    assert completed.status is RunStatus.COMPLETED
    assert hook.calls == [
        "normalize",
        "discover",
        "chemistry",
        "chemistry",
        "evidence",
        "proposal",
        "review",
        "finalize",
    ]
    service.close()


def test_cancel_wins_completion_race(tmp_path: Path) -> None:
    hook = NodeController(block_normalize=True)
    service = make_service(tmp_path, hook)
    service.create(request())
    assert hook.entered.wait(timeout=5)

    cancelled = service.cancel("workflow-run")
    assert cancelled.status is RunStatus.CANCELLED
    hook.release.set()
    assert service.wait_for_idle(timeout=5)
    assert service.get("workflow-run").status is RunStatus.CANCELLED
    service.close()


def test_sqlite_run_survives_service_reconstruction(tmp_path: Path) -> None:
    first = make_service(tmp_path, durable_checkpoints=True)
    first.create(request("durable-run"))
    assert first.wait_for_idle(timeout=5)
    expected = first.get("durable-run")
    first.close()

    second = make_service(tmp_path, durable_checkpoints=True)
    assert second.get("durable-run") == expected
    second.close()


def test_checkpoint_restart_resumes_failed_node(tmp_path: Path) -> None:
    first_hook = NodeController(fail_chemistry_once=True)
    first = make_service(tmp_path, first_hook, durable_checkpoints=True)
    first.create(request("restart-run"))
    assert first.wait_for_idle(timeout=5)
    assert first.get("restart-run").status is RunStatus.FAILED
    first.close()

    second_hook = NodeController()
    second = make_service(tmp_path, second_hook, durable_checkpoints=True)
    assert second.resume("restart-run").status is RunStatus.RUNNING
    assert second.wait_for_idle(timeout=5)
    assert second.get("restart-run").status is RunStatus.COMPLETED
    restarted_result = second.get("restart-run").analysis_result
    assert restarted_result is not None
    assert restarted_result.proposal is not None
    assert restarted_result.proposal_review is not None
    assert second_hook.calls == ["chemistry", "evidence", "proposal", "review", "finalize"]
    second.close()


@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
def test_resume_rejects_non_failed_terminal_states(tmp_path: Path, terminal: str) -> None:
    hook = NodeController(block_normalize=terminal == "cancelled")
    service = make_service(tmp_path, hook)
    service.create(request())
    if terminal == "cancelled":
        assert hook.entered.wait(timeout=5)
        service.cancel("workflow-run")
        hook.release.set()
    assert service.wait_for_idle(timeout=5)

    with pytest.raises(RunConflictError, match=f"status '{terminal}'"):
        service.resume("workflow-run")
    service.close()


def test_resume_api_requires_authentication_and_reports_conflict(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create(request("api-resume"))
    assert service.wait_for_idle(timeout=5)
    app.dependency_overrides[get_run_service] = lambda: service
    client = TestClient(app)
    try:
        unauthorized = client.post("/internal/v1/runs/api-resume/resume")
        assert unauthorized.status_code == 401
        conflict = client.post(
            "/internal/v1/runs/api-resume/resume",
            headers={"X-Agent-Token": "test-only-agent-token"},
        )
        assert conflict.status_code == 409
        assert conflict.json() == {
            "detail": "Run 'api-resume' cannot be resumed from status 'completed'"
        }
    finally:
        app.dependency_overrides.clear()
        service.close()


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()
