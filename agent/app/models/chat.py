from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _to_rfc3339(value: datetime) -> str:
    """序列化为 Go time.Time 可解析的 RFC3339；MySQL 取回的 naive 时间按 UTC 补齐。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")

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

    role: Literal["user", "assistant"] = Field(description="对话角色：用户或助手")
    content: str = Field(
        min_length=1, max_length=32768, description="消息内容", examples=["请分析下大黄的毒性。"]
    )


class ChatTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="对话回合的唯一标识符",
        examples=["turn_12345"],
    )
    session_id: str = Field(
        min_length=1, max_length=128, description="对话会话 ID", examples=["sess_67890"]
    )
    user_id: str = Field(
        min_length=1, max_length=128, description="用户唯一标识符", examples=["user_abc"]
    )
    message: str = Field(
        min_length=1,
        max_length=32768,
        description="当前用户输入的提问消息",
        examples=["大黄有哪些已知的毒性成分？"],
    )
    history: list[ChatHistoryMessage] = Field(
        default_factory=list, max_length=100, description="对话历史记录，用于上下文理解"
    )


class ChatEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1, description="事件序列号，用于顺序排序")
    type: EventType = Field(description="事件类型，如节点开始、工具调用等")
    node: str = Field(description="产生事件的图节点名称")
    status: str = Field(description="事件状态")
    detail: str = Field(description="事件的详细描述文本")
    delta: str | None = Field(default=None, description="助手消息的增量内容（仅在增量输出时存在）")
    tool_name: str | None = Field(default=None, description="调用的工具名称")
    tool_call_id: str | None = Field(default=None, description="工具调用的唯一标识符")
    input: Any | None = Field(default=None, description="输入参数的脱敏副本")
    output: Any | None = Field(default=None, description="输出结果的脱敏副本")
    created_at: datetime = Field(description="事件创建时间")

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _to_rfc3339(value)


class ChatTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(description="对话回合标识符")
    session_id: str = Field(description="所属会话标识符")
    status: ChatStatus = Field(description="当前回合的执行状态")
    events: list[ChatEvent] = Field(description="该回合内产生的所有处理事件")
    assistant_message: str | None = Field(default=None, description="助手的最终回答内容")
    error_message: str | None = Field(default=None, description="执行失败时的错误信息")
    created_at: datetime = Field(description="回合创建时间")
    updated_at: datetime = Field(description="最后更新时间")

    @field_serializer("created_at", "updated_at")
    def _serialize_times(self, value: datetime) -> str:
        return _to_rfc3339(value)
