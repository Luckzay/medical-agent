from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from app.models.chat import ChatEvent, ChatTurnCreate, ChatTurnResponse


class DuplicateChatTurnError(RuntimeError):
    pass


class ChatTurnNotFoundError(RuntimeError):
    pass


class SQLiteChatRepository:
    """Durable chat turn/event store; every event is committed for incremental polling."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._ensure_connection()

    def _ensure_connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                connection = sqlite3.connect(self._path, check_same_thread=False, timeout=5.0)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=5000")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS chat_turns (
                        turn_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        message TEXT NOT NULL,
                        history_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        assistant_message TEXT,
                        error_message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS chat_events (
                        turn_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        node TEXT NOT NULL,
                        status TEXT NOT NULL,
                        detail TEXT NOT NULL,
                        delta TEXT,
                        tool_name TEXT,
                        tool_call_id TEXT,
                        input_json TEXT,
                        output_json TEXT,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (turn_id, sequence),
                        FOREIGN KEY (turn_id) REFERENCES chat_turns(turn_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_chat_events_turn
                    ON chat_events(turn_id, sequence);
                    """
                )
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(chat_events)")
                }
                if "delta" not in columns:
                    connection.execute("ALTER TABLE chat_events ADD COLUMN delta TEXT")
                connection.commit()
                self._connection = connection
            return self._connection

    def create(self, request: ChatTurnCreate) -> ChatTurnResponse:
        import json

        now = datetime.now(UTC).isoformat()
        connection = self._ensure_connection()
        try:
            with self._lock:
                connection.execute(
                    "INSERT INTO chat_turns VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)",
                    (
                        request.turn_id,
                        request.session_id,
                        request.user_id,
                        request.message,
                        json.dumps([item.model_dump() for item in request.history]),
                        now,
                        now,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateChatTurnError(request.turn_id) from exc
        return self.get(request.turn_id)

    def load_request(self, turn_id: str) -> ChatTurnCreate:
        import json

        connection = self._ensure_connection()
        with self._lock:
            row = connection.execute(
                "SELECT * FROM chat_turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
        if row is None:
            raise ChatTurnNotFoundError(turn_id)
        return ChatTurnCreate(
            turn_id=row["turn_id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            message=row["message"],
            history=json.loads(row["history_json"]),
        )

    def set_status(
        self,
        turn_id: str,
        status: str,
        *,
        assistant_message: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        connection = self._ensure_connection()
        with self._lock:
            cursor = connection.execute(
                """UPDATE chat_turns SET status = ?, assistant_message = ?,
                   error_message = ?, updated_at = ? WHERE turn_id = ?""",
                (status, assistant_message, error_message, now, turn_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise ChatTurnNotFoundError(turn_id)

    def append_event(self, turn_id: str, event: ChatEvent) -> None:
        import json

        connection = self._ensure_connection()
        with self._lock:
            connection.execute(
                """INSERT INTO chat_events
                   (turn_id, sequence, type, node, status, detail, delta, tool_name,
                    tool_call_id, input_json, output_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn_id,
                    event.sequence,
                    event.type,
                    event.node,
                    event.status,
                    event.detail,
                    event.delta,
                    event.tool_name,
                    event.tool_call_id,
                    json.dumps(event.input, ensure_ascii=False)
                    if event.input is not None
                    else None,
                    json.dumps(event.output, ensure_ascii=False)
                    if event.output is not None
                    else None,
                    event.created_at.isoformat(),
                ),
            )
            connection.execute(
                "UPDATE chat_turns SET updated_at = ? WHERE turn_id = ?",
                (event.created_at.isoformat(), turn_id),
            )
            connection.commit()

    def next_sequence(self, turn_id: str) -> int:
        connection = self._ensure_connection()
        with self._lock:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM chat_events WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()
        return int(row["value"])

    def list_recoverable(self) -> list[str]:
        connection = self._ensure_connection()
        with self._lock:
            rows = connection.execute(
                "SELECT turn_id FROM chat_turns WHERE status IN ('pending', 'running')"
            ).fetchall()
        return [str(row["turn_id"]) for row in rows]

    def get(self, turn_id: str) -> ChatTurnResponse:
        import json

        connection = self._ensure_connection()
        with self._lock:
            row = connection.execute(
                "SELECT * FROM chat_turns WHERE turn_id = ?", (turn_id,)
            ).fetchone()
            event_rows = connection.execute(
                "SELECT * FROM chat_events WHERE turn_id = ? ORDER BY sequence", (turn_id,)
            ).fetchall()
        if row is None:
            raise ChatTurnNotFoundError(turn_id)
        events = [
            ChatEvent(
                sequence=item["sequence"],
                type=item["type"],
                node=item["node"],
                status=item["status"],
                detail=item["detail"],
                delta=item["delta"],
                tool_name=item["tool_name"],
                tool_call_id=item["tool_call_id"],
                input=json.loads(item["input_json"]) if item["input_json"] else None,
                output=json.loads(item["output_json"]) if item["output_json"] else None,
                created_at=item["created_at"],
            )
            for item in event_rows
        ]
        return ChatTurnResponse(
            turn_id=row["turn_id"],
            session_id=row["session_id"],
            status=row["status"],
            events=events,
            assistant_message=row["assistant_message"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        with self._lock:
            connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()
