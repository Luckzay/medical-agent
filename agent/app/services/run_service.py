from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from functools import partial
from pathlib import Path
from threading import RLock

from app.core.config import Settings, get_settings
from app.models.run import RunCreate, RunResponse, RunStatus, WorkflowStatus
from app.services.analysis_service import AnalysisService
from app.services.builtin_tools import build_tool_registry
from app.services.evidence_store import EvidenceStore
from app.services.run_repository import (
    DuplicateRunRepositoryError,
    SQLiteRunRepository,
)
from app.services.tool_runtime import ToolRuntime
from app.services.workflow import AnalysisWorkflow, LangGraphAnalysisWorkflow


class DuplicateRunError(Exception):
    """Raised when a run identifier is already present."""


class RunNotFoundError(Exception):
    """Raised when a run identifier cannot be found."""


class RunConflictError(Exception):
    """Raised when a state transition is not allowed."""


class RunService:
    """Durable asynchronous run service backed by a checkpointed workflow."""

    def __init__(
        self,
        analysis_service: AnalysisService | None = None,
        workflow: AnalysisWorkflow | None = None,
        repository: SQLiteRunRepository | None = None,
        runtime: ToolRuntime | None = None,
        *,
        settings: Settings | None = None,
        database_path: str | Path | None = None,
        worker_count: int | None = None,
    ) -> None:
        configured = settings or get_settings()
        analysis = analysis_service or AnalysisService(configured)
        self._evidence_store = EvidenceStore(
            configured.evidence_source_path, configured.evidence_database_path
        )
        self._runtime = runtime or ToolRuntime(
            build_tool_registry(analysis, self._evidence_store),
            database_path or configured.database_path,
        )
        self._workflow = workflow or LangGraphAnalysisWorkflow(
            analysis, checkpoint_path=configured.checkpoint_path, runtime=self._runtime
        )
        self._repository = repository or SQLiteRunRepository(
            database_path or configured.database_path
        )
        self._worker_count = worker_count or configured.worker_count
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=self._worker_count, thread_name_prefix="agent-run"
        )
        self._futures: set[Future[None]] = set()
        self._scheduled_run_ids: set[str] = set()
        self._shutdown = False
        self._closed = False

    def _ensure_executor(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("RunService is closed")
            if self._shutdown:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._worker_count, thread_name_prefix="agent-run"
                )
                self._shutdown = False

    def _submit(
        self, run_id: str, herbs: list[str], research_goal: str | None, *, resume: bool
    ) -> None:
        self._ensure_executor()
        with self._lock:
            if run_id in self._scheduled_run_ids:
                return
            self._scheduled_run_ids.add(run_id)
            future = self._executor.submit(
                self._execute, run_id, herbs, research_goal, resume=resume
            )
            self._futures.add(future)
            future.add_done_callback(partial(self._done, run_id))

    def _done(self, run_id: str, future: Future[None]) -> None:
        with self._lock:
            self._futures.discard(future)
            self._scheduled_run_ids.discard(run_id)

    def create(self, request: RunCreate) -> RunResponse:
        try:
            running = self._repository.create(request)
        except DuplicateRunRepositoryError as exc:
            raise DuplicateRunError(request.run_id) from exc
        self._submit(request.run_id, list(request.herbs), request.research_goal, resume=False)
        return running

    def resume(self, run_id: str) -> RunResponse:
        run = self._require(run_id)
        if run.status is not RunStatus.FAILED:
            raise RunConflictError(
                f"Run '{run_id}' cannot be resumed from status '{run.status.value}'"
            )
        workflow = self._workflow.metadata(run_id, WorkflowStatus.RUNNING)
        running = self._repository.update(
            run_id,
            expected_status=RunStatus.FAILED,
            status=RunStatus.RUNNING,
            workflow=workflow,
            error_message=None,
        )
        if running is None:
            current = self._require(run_id)
            raise RunConflictError(
                f"Run '{run_id}' cannot be resumed from status '{current.status.value}'"
            )
        self._submit(run_id, list(running.herbs), running.research_goal, resume=True)
        return running

    def recover_running_tasks(self) -> None:
        """Schedule durable running records, resuming only when a checkpoint exists."""
        for run in self._repository.list_by_status(RunStatus.RUNNING):
            self._submit(
                run.run_id,
                list(run.herbs),
                run.research_goal,
                resume=self._workflow.has_checkpoint(run.run_id),
            )

    def _execute(
        self,
        run_id: str,
        herbs: list[str],
        research_goal: str | None,
        *,
        resume: bool,
    ) -> None:
        try:
            result = (
                self._workflow.resume(run_id)
                if resume and self._workflow.has_checkpoint(run_id)
                else (
                    self._workflow.invoke(run_id, herbs)
                    if research_goal is None
                    else self._workflow.invoke(run_id, herbs, research_goal)
                )
            )
        except Exception as exc:
            try:
                workflow = self._workflow.metadata(run_id, WorkflowStatus.FAILED)
            except Exception:
                workflow = None
            self._repository.update(
                run_id,
                expected_status=RunStatus.RUNNING,
                status=RunStatus.FAILED,
                workflow=workflow,
                error_message=str(exc) or type(exc).__name__,
            )
            return

        workflow = result.workflow or self._workflow.metadata(run_id, WorkflowStatus.COMPLETED)
        self._repository.update(
            run_id,
            expected_status=RunStatus.RUNNING,
            status=RunStatus.COMPLETED,
            analysis_result=result,
            workflow=workflow,
            error_message=None,
        )

    def _require(self, run_id: str) -> RunResponse:
        run = self._repository.get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    @property
    def runtime(self) -> ToolRuntime:
        return self._runtime

    @property
    def evidence_store(self) -> EvidenceStore:
        return self._evidence_store

    def get(self, run_id: str) -> RunResponse:
        return self._require(run_id)

    def cancel(self, run_id: str) -> RunResponse:
        run = self._require(run_id)
        if run.status not in (RunStatus.RUNNING, RunStatus.FAILED):
            return run
        self._workflow.cancel(run_id)
        workflow = self._workflow.metadata(run_id, WorkflowStatus.CANCELLED)
        cancelled = self._repository.update(
            run_id,
            expected_status=(RunStatus.RUNNING, RunStatus.FAILED),
            status=RunStatus.CANCELLED,
            analysis_result=run.analysis_result,
            workflow=workflow,
            error_message=run.error_message,
        )
        return cancelled or self._require(run_id)

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """Wait for currently submitted work; intended for deterministic tests only."""
        with self._lock:
            futures = set(self._futures)
        if not futures:
            return True
        _done, pending = wait(futures, timeout=timeout)
        return not pending

    def clear(self) -> None:
        """Remove all runs and checkpoints; intended for isolated tests."""
        self.wait_for_idle()
        self._repository.clear()
        self._workflow.clear()

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            executor = self._executor
            self._shutdown = True
        # ThreadPoolExecutor.shutdown is idempotent; a later wait=True call must still
        # join work after an earlier non-blocking shutdown before resources are closed.
        executor.shutdown(wait=wait, cancel_futures=False)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
        self.shutdown(wait=True)
        self._workflow.close()
        self._runtime.close()
        self._repository.close()
        self._evidence_store.close()
        with self._lock:
            self._closed = True


run_service = RunService()
