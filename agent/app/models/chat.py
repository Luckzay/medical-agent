from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["system", "user", "assistant", "tool"]
ChatStatus = Literal["pending", "running", "completed", "failed"]
EventType = Literal[
    "node_start",
    "node_end",
    "llm_start",
    "llm_end",
    "assistant_delta",
    "tool_call",
    "tool_result",
    "error",
]


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=32768)


class ChatTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    session_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=32768)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=100)


class ChatEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    type: EventType
    node: str
    status: str
    detail: str
    delta: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    input: Any | None = None
    output: Any | None = None
    created_at: datetime


class ChatTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    session_id: str
    status: ChatStatus
    events: list[ChatEvent]
    assistant_message: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
