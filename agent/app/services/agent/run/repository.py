from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

import pymysql  # type: ignore[import-untyped]

from app.models.run import AnalysisResult, RunCreate, RunResponse, RunStatus, WorkflowMetadata
from app.services.infrastructure.mysql import MySQLDatabase


class DuplicateRunRepositoryError(Exception):
    """Raised when an atomic insert encounters an existing run identifier."""


class MySQLRunRepository:
    """MySQL-backed run store with atomic conditional state transitions."""

    def __init__(self, database: MySQLDatabase | None = None) -> None:
        self.database = database or MySQLDatabase()

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    def create(self, request: RunCreate) -> RunResponse:
        now = self._now()
        run = RunResponse(
            **request.model_dump(), status=RunStatus.RUNNING, created_at=now, updated_at=now
        )
        try:
            with self.database.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO agent_workflow_runs
                    (run_id,user_id,trace_id,herbs_json,research_goal,status,
                     analysis_result_json,workflow_json,error_message,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,%s,%s)""",
                    (
                        request.run_id,
                        request.user_id,
                        request.trace_id,
                        self._json(request.herbs),
                        request.research_goal,
                        RunStatus.RUNNING.value,
                        now,
                        now,
                    ),
                )
        except pymysql.err.IntegrityError as exc:
            raise DuplicateRunRepositoryError(request.run_id) from exc
        return run

    @staticmethod
    def _from_row(row: Mapping[str, object]) -> RunResponse:
        analysis_json = row["analysis_result_json"]
        workflow_json = row["workflow_json"]
        return RunResponse(
            run_id=row["run_id"],
            user_id=row["user_id"],
            trace_id=row["trace_id"],
            herbs=json.loads(str(row["herbs_json"])),
            research_goal=row["research_goal"],
            status=RunStatus(str(row["status"])),
            analysis_result=(
                AnalysisResult.model_validate_json(str(analysis_json)) if analysis_json else None
            ),
            workflow=(
                WorkflowMetadata.model_validate_json(str(workflow_json)) if workflow_json else None
            ),
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get(self, run_id: str) -> RunResponse | None:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT * FROM agent_workflow_runs WHERE run_id=%s", (run_id,))
            row = cursor.fetchone()
        return None if row is None else self._from_row(row)

    def list_by_status(self, status: RunStatus) -> list[RunResponse]:
        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM agent_workflow_runs WHERE status=%s ORDER BY created_at",
                (status.value,),
            )
            rows = cursor.fetchall()
        return [self._from_row(row) for row in rows]

    def list_run_ids(self) -> list[str]:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT run_id FROM agent_workflow_runs")
            rows = cursor.fetchall()
        return [str(row["run_id"]) for row in rows]

    def update(
        self,
        run_id: str,
        *,
        expected_status: RunStatus | Iterable[RunStatus],
        status: RunStatus,
        analysis_result: AnalysisResult | None = None,
        workflow: WorkflowMetadata | None = None,
        error_message: str | None = None,
    ) -> RunResponse | None:
        expected = (
            (expected_status,) if isinstance(expected_status, RunStatus) else tuple(expected_status)
        )
        if not expected:
            raise ValueError("expected_status must not be empty")
        placeholders = ",".join("%s" for _ in expected)
        now = self._now()
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""UPDATE agent_workflow_runs
                    SET status=%s,analysis_result_json=%s,workflow_json=%s,
                        error_message=%s,updated_at=%s
                    WHERE run_id=%s AND status IN ({placeholders})""",
                    (
                        status.value,
                        analysis_result.model_dump_json() if analysis_result else None,
                        workflow.model_dump_json() if workflow else None,
                        error_message,
                        now,
                        run_id,
                        *(item.value for item in expected),
                    ),
                )
                if cursor.rowcount != 1:
                    return None
                cursor.execute("SELECT * FROM agent_workflow_runs WHERE run_id=%s", (run_id,))
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("updated run disappeared")
        return self._from_row(row)

    def clear(self) -> None:
        with self.database.cursor() as cursor:
            cursor.execute("DELETE FROM agent_workflow_runs")

    def close(self) -> None:
        pass
