from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from app.models.run import AnalysisResult, RunCreate, RunResponse, RunStatus, WorkflowMetadata


class DuplicateRunRepositoryError(Exception):
    """Raised when an atomic insert encounters an existing run identifier."""


class SQLiteRunRepository:
    """SQLite-backed run store with serialized writes and conditional transitions."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                trace_id TEXT NOT NULL,
                herbs_json TEXT NOT NULL,
                research_goal TEXT,
                status TEXT NOT NULL,
                analysis_result_json TEXT,
                workflow_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
        self._connection.commit()

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def create(self, request: RunCreate) -> RunResponse:
        now = self._now()
        run = RunResponse(
            **request.model_dump(),
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            try:
                self._connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, user_id, trace_id, herbs_json, research_goal, status,
                        analysis_result_json, workflow_json, error_message,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        request.run_id,
                        request.user_id,
                        request.trace_id,
                        self._json(request.herbs),
                        request.research_goal,
                        RunStatus.RUNNING.value,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise DuplicateRunRepositoryError(request.run_id) from exc
        return run

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RunResponse:
        analysis_json = row["analysis_result_json"]
        workflow_json = row["workflow_json"]
        return RunResponse(
            run_id=row["run_id"],
            user_id=row["user_id"],
            trace_id=row["trace_id"],
            herbs=json.loads(row["herbs_json"]),
            research_goal=row["research_goal"],
            status=RunStatus(row["status"]),
            analysis_result=(
                AnalysisResult.model_validate_json(analysis_json) if analysis_json else None
            ),
            workflow=(
                WorkflowMetadata.model_validate_json(workflow_json) if workflow_json else None
            ),
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get(self, run_id: str) -> RunResponse | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_by_status(self, status: RunStatus) -> list[RunResponse]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM runs WHERE status = ? ORDER BY created_at", (status.value,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_run_ids(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute("SELECT run_id FROM runs").fetchall()
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
        placeholders = ",".join("?" for _ in expected)
        now = self._now()
        parameters: list[object] = [
            status.value,
            analysis_result.model_dump_json() if analysis_result is not None else None,
            workflow.model_dump_json() if workflow is not None else None,
            error_message,
            now.isoformat(),
            run_id,
            *(item.value for item in expected),
        ]
        with self._lock:
            cursor = self._connection.execute(
                f"""
                UPDATE runs
                SET status = ?, analysis_result_json = ?, workflow_json = ?,
                    error_message = ?, updated_at = ?
                WHERE run_id = ? AND status IN ({placeholders})
                """,
                parameters,
            )
            self._connection.commit()
            if cursor.rowcount != 1:
                return None
            row = self._connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("updated run disappeared")
        return self._from_row(row)

    def clear(self) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM runs")
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True
