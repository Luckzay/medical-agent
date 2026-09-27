from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from threading import RLock
from typing import cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.models.tooling import ToolAudit, ToolExecutionContext
from app.services.mysql import MySQLDatabase
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
    """Permissioned tool executor with a payload-free durable MySQL audit trail."""

    def __init__(self, registry: ToolRegistry, database: MySQLDatabase | None = None) -> None:
        self.registry = registry
        self._database = database or MySQLDatabase()
        self._lock = RLock()
        self._executor: ThreadPoolExecutor | None = None

    def _executor_for_use(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent-tool")
            return self._executor

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
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
        with self._database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO agent_tool_audits
                (audit_id,run_id,node,tool_name,tool_version,started_at,completed_at,
                 duration_ms,status,attempts,error_type,error_message)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    uuid4().hex,
                    context.run_id,
                    context.node,
                    tool_name,
                    tool_version,
                    started.replace(tzinfo=None),
                    completed.replace(tzinfo=None),
                    max(0, round((time.monotonic() - started_clock) * 1000)),
                    status,
                    attempts,
                    type(error).__name__ if error is not None else None,
                    self._safe_error(error) if error is not None else None,
                ),
            )

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
                future = self._executor_for_use().submit(definition.handler, validated_input)
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
        with self._database.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM agent_tool_audits WHERE run_id=%s ORDER BY started_at,audit_id",
                (run_id,),
            )
            rows = cursor.fetchall()
        return [ToolAudit.model_validate(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)
