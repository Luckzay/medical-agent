from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.models.tooling import ToolAudit, ToolExecutionContext
from app.services.tool_registry import ToolRegistry


class ToolExecutionError(RuntimeError):
    pass


class ToolPermissionError(ToolExecutionError):
    pass


class ToolInputValidationError(ToolExecutionError):
    pass


class ToolOutputValidationError(ToolExecutionError):
    pass


class ToolTimeoutError(ToolExecutionError):
    pass


class ToolRuntime:
    """Permissioned tool executor with a payload-free durable SQLite audit trail."""

    def __init__(self, registry: ToolRegistry, database_path: str | Path) -> None:
        self.registry = registry
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._ensure_resources()

    def _ensure_resources(self) -> tuple[sqlite3.Connection, ThreadPoolExecutor]:
        with self._lock:
            if self._connection is None:
                connection = sqlite3.connect(
                    self._database_path, check_same_thread=False, timeout=5.0
                )
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=5000")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tool_audits (
                        audit_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        node TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        tool_version TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL,
                        error_type TEXT,
                        error_message TEXT
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tool_audits_run "
                    "ON tool_audits(run_id, started_at)"
                )
                connection.commit()
                self._connection = connection
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent-tool")
            return self._connection, self._executor

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        # Deliberately excludes payloads and validation details, which can contain input values.
        if isinstance(exc, ValidationError):
            return "Tool data did not match the declared schema"
        message = str(exc).replace("\n", " ").strip()
        return (message or type(exc).__name__)[:300]

    def _audit(
        self,
        *,
        context: ToolExecutionContext,
        tool_name: str,
        tool_version: str,
        started: datetime,
        started_clock: float,
        status: str,
        attempts: int,
        error: BaseException | None,
    ) -> None:
        completed = datetime.now(UTC)
        row = (
            uuid4().hex,
            context.run_id,
            context.node,
            tool_name,
            tool_version,
            started.isoformat(),
            completed.isoformat(),
            max(0, round((time.monotonic() - started_clock) * 1000)),
            status,
            attempts,
            type(error).__name__ if error is not None else None,
            self._safe_error(error) if error is not None else None,
        )
        connection, _ = self._ensure_resources()
        with self._lock:
            connection.execute(
                "INSERT INTO tool_audits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            connection.commit()

    def execute(self, name: str, payload: object, context: ToolExecutionContext) -> BaseModel:
        definition = self.registry.get_tool(name)
        started = datetime.now(UTC)
        started_clock = time.monotonic()
        attempts = 0
        error: BaseException | None = None
        status = "failed"
        try:
            missing = definition.required_permissions - context.permissions
            if missing:
                raise ToolPermissionError(
                    f"Missing required permissions: {', '.join(sorted(missing))}"
                )
            try:
                validated_input = definition.input_model.model_validate(payload)
            except ValidationError as exc:
                raise ToolInputValidationError("Invalid tool input") from exc

            max_attempts = 1 + definition.retry_policy.max_retries
            for attempts in range(1, max_attempts + 1):
                _, executor = self._ensure_resources()
                future = executor.submit(definition.handler, validated_input)
                try:
                    raw_output = future.result(timeout=definition.timeout_seconds)
                    try:
                        output = definition.output_model.model_validate(raw_output)
                    except ValidationError as exc:
                        raise ToolOutputValidationError("Invalid tool output") from exc
                    status = "success"
                    return cast(BaseModel, output)
                except FutureTimeoutError:
                    future.cancel()
                    error = ToolTimeoutError(
                        f"Tool exceeded {definition.timeout_seconds:g}s timeout"
                    )
                except ToolOutputValidationError:
                    raise
                except Exception as exc:
                    error = exc
                if attempts == max_attempts:
                    if isinstance(error, ToolTimeoutError):
                        raise error
                    raise ToolExecutionError("Tool handler failed") from error
            raise AssertionError("unreachable")
        except BaseException as exc:
            error = exc
            if isinstance(exc, ToolPermissionError):
                status = "permission_denied"
            elif isinstance(exc, ToolInputValidationError):
                status = "input_validation_failed"
            elif isinstance(exc, ToolOutputValidationError):
                status = "output_validation_failed"
            elif isinstance(exc, ToolTimeoutError):
                status = "timeout"
            else:
                status = "error"
            raise
        finally:
            self._audit(
                context=context,
                tool_name=definition.name,
                tool_version=definition.version,
                started=started,
                started_clock=started_clock,
                status=status,
                attempts=attempts,
                error=error,
            )

    def audits_for_run(self, run_id: str) -> list[ToolAudit]:
        connection, _ = self._ensure_resources()
        with self._lock:
            rows = connection.execute(
                "SELECT * FROM tool_audits WHERE run_id = ? ORDER BY started_at, audit_id",
                (run_id,),
            ).fetchall()
        return [ToolAudit.model_validate(dict(row)) for row in rows]

    def close(self) -> None:
        with self._lock:
            connection, executor = self._connection, self._executor
            self._connection = None
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)
        if connection is not None:
            connection.close()
