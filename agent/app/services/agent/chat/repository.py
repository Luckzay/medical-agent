from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

import pymysql  # type: ignore[import-untyped]

from app.models.chat import ChatEvent, ChatTurnCreate, ChatTurnResponse
from app.services.infrastructure.mysql import MySQLDatabase


class DuplicateChatTurnError(RuntimeError):
    pass


class ChatTurnNotFoundError(RuntimeError):
    pass


class MySQLChatRepository:
    """Durable chat store with transactionally allocated per-turn event sequences."""

    def __init__(self, database: MySQLDatabase | None = None) -> None:
        self.database = database or MySQLDatabase()

    def create(self, request: ChatTurnCreate) -> ChatTurnResponse:
        now = datetime.now(UTC).replace(tzinfo=None)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO agent_chat_turns
                    (turn_id,session_id,user_id,message,history_json,status,
                     assistant_message,error_message,next_event_sequence,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,'pending',NULL,NULL,1,%s,%s)""",
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
        except pymysql.err.IntegrityError:
            # Go 后端在调用本服务前会预创建 pending 行；也可能是同一回合的重复投递。
            # 走幂等补齐而不是直接判冲突。
            self._adopt_existing_turn(request, now)
        return self.get(request.turn_id)

    def _adopt_existing_turn(self, request: ChatTurnCreate, now: object) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT session_id,user_id,status FROM agent_chat_turns WHERE turn_id=%s FOR UPDATE",
                (request.turn_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise DuplicateChatTurnError(request.turn_id)
        if str(row["session_id"]) != request.session_id or str(row["user_id"]) != request.user_id:
            raise DuplicateChatTurnError(request.turn_id)
        # 已结束回合的重复投递：原样返回，不重置状态
        if row["status"] in ("completed", "failed"):
            return
        # pending/running：Go 预创建的行缺少 message/history，补齐后后台线程即可接管
        with self.database.cursor() as cursor:
            cursor.execute(
                """UPDATE agent_chat_turns
                   SET message=%s,history_json=%s,error_message=NULL,updated_at=%s
                   WHERE turn_id=%s""",
                (
                    request.message,
                    json.dumps([item.model_dump() for item in request.history]),
                    now,
                    request.turn_id,
                ),
            )
        if cursor.rowcount == 0:
            raise DuplicateChatTurnError(request.turn_id)

    def load_request(self, turn_id: str) -> ChatTurnCreate:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT * FROM agent_chat_turns WHERE turn_id=%s", (turn_id,))
            row = cursor.fetchone()
        if row is None:
            raise ChatTurnNotFoundError(turn_id)
        return ChatTurnCreate(
            turn_id=row["turn_id"],
            # 旧结构中这两列为 bigint，模型层统一按字符串标识处理
            session_id=str(row["session_id"]),
            user_id=str(row["user_id"]),
            message=row["message"],
            history=json.loads(str(row["history_json"])),
        )

    def set_status(
        self,
        turn_id: str,
        status: str,
        *,
        assistant_message: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """UPDATE agent_chat_turns SET status=%s,assistant_message=%s,
                error_message=%s,updated_at=%s WHERE turn_id=%s""",
                (
                    status,
                    assistant_message,
                    error_message,
                    datetime.now(UTC).replace(tzinfo=None),
                    turn_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ChatTurnNotFoundError(turn_id)

    def append_event(self, turn_id: str, event: ChatEvent) -> int:
        """Lock the parent turn and allocate/insert one sequence in the same transaction."""
        with self.database.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT next_event_sequence FROM agent_chat_turns WHERE turn_id=%s FOR UPDATE",
                    (turn_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ChatTurnNotFoundError(turn_id)
                sequence = int(row["next_event_sequence"])
                cursor.execute(
                    """INSERT INTO agent_chat_events
                    (turn_id,sequence,type,node,status,detail,delta,tool_name,tool_call_id,
                     input_json,output_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        turn_id,
                        sequence,
                        event.type,
                        event.node,
                        event.status,
                        event.detail,
                        event.delta,
                        event.tool_name,
                        event.tool_call_id,
                        (
                            json.dumps(event.input, ensure_ascii=False)
                            if event.input is not None
                            else None
                        ),
                        json.dumps(event.output, ensure_ascii=False)
                        if event.output is not None
                        else None,
                        event.created_at.replace(tzinfo=None),
                    ),
                )
                cursor.execute(
                    """UPDATE agent_chat_turns
                    SET next_event_sequence=next_event_sequence+1,updated_at=%s
                    WHERE turn_id=%s""",
                    (event.created_at.replace(tzinfo=None), turn_id),
                )
        return sequence

    def next_sequence(self, turn_id: str) -> int:
        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT next_event_sequence FROM agent_chat_turns WHERE turn_id=%s", (turn_id,)
            )
            row = cursor.fetchone()
        if row is None:
            raise ChatTurnNotFoundError(turn_id)
        return int(row["next_event_sequence"])

    def list_recoverable(self) -> list[str]:
        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT turn_id FROM agent_chat_turns WHERE status IN ('pending','running')"
            )
            rows = cursor.fetchall()
        return [str(row["turn_id"]) for row in rows]

    @staticmethod
    def _event(row: Mapping[str, object]) -> ChatEvent:
        return ChatEvent(
            sequence=row["sequence"],
            type=row["type"],
            node=row["node"],
            status=row["status"],
            detail=row["detail"],
            delta=row["delta"],
            tool_name=row["tool_name"],
            tool_call_id=row["tool_call_id"],
            input=json.loads(str(row["input_json"])) if row["input_json"] else None,
            output=json.loads(str(row["output_json"])) if row["output_json"] else None,
            created_at=row["created_at"],
        )

    def get(self, turn_id: str) -> ChatTurnResponse:
        with self.database.cursor() as cursor:
            cursor.execute("SELECT * FROM agent_chat_turns WHERE turn_id=%s", (turn_id,))
            row = cursor.fetchone()
            if row is not None:
                cursor.execute(
                    "SELECT * FROM agent_chat_events WHERE turn_id=%s ORDER BY sequence", (turn_id,)
                )
                event_rows = cursor.fetchall()
            else:
                event_rows = []
        if row is None:
            raise ChatTurnNotFoundError(turn_id)
        return ChatTurnResponse(
            turn_id=row["turn_id"],
            session_id=str(row["session_id"]),
            status=row["status"],
            events=[self._event(item) for item in event_rows],
            assistant_message=row["assistant_message"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        pass
