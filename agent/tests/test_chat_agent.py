from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.routes import get_chat_service
from app.core.config import Settings
from app.main import app
from app.models.chat import ChatTurnCreate
from app.models.tooling import ToolDefinition
from app.services.chat_repository import SQLiteChatRepository
from app.services.chat_service import ChatTurnService
from app.services.llm_proxy import LLMChatResult, LLMToolCall, LLMToolCallFunction
from app.services.tool_registry import ToolRegistry
from app.services.tool_runtime import ToolRuntime


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class EchoOutput(BaseModel):
    value: str


class ScriptedLLM:
    def __init__(
        self, results: list[LLMChatResult], gate: tuple[Event, Event] | None = None
    ) -> None:
        self.results = results
        self.gate = gate
        self.messages: list[list[dict[str, Any]]] = []

    def stream_chat(
        self, *, on_delta: Callable[[str], None] | None = None, **kwargs: Any
    ) -> LLMChatResult:
        self.messages.append(kwargs["messages"])
        if self.gate is not None:
            self.gate[0].set()
            assert self.gate[1].wait(2)
        result = self.results.pop(0)
        if result.content and on_delta is not None:
            on_delta(result.content)
        return result


class StreamingGateLLM:
    def __init__(self, emitted: Event, release: Event) -> None:
        self.emitted = emitted
        self.release = release

    def stream_chat(
        self, *, on_delta: Callable[[str], None] | None = None, **_kwargs: Any
    ) -> LLMChatResult:
        assert on_delta is not None
        on_delta("首个 token=secret-value")
        self.emitted.set()
        assert self.release.wait(2)
        on_delta("完成")
        return LLMChatResult(content="首个 token=secret-value完成")


def tool_call(call_id: str = "call-1", value: str = "黄芪") -> LLMChatResult:
    return LLMChatResult(
        tool_calls=[
            LLMToolCall(
                id=call_id,
                function=LLMToolCallFunction(
                    name="normalize_herbs", arguments=f'{{"value":"{value}"}}'
                ),
            )
        ]
    )


@pytest.fixture
def service_factory(tmp_path: Path) -> Iterator[Any]:
    services: list[ChatTurnService] = []

    def factory(
        responses: list[LLMChatResult],
        *,
        handler: Callable[[EchoInput], EchoOutput] | None = None,
        max_rounds: int = 8,
        max_calls: int = 12,
        gate: tuple[Event, Event] | None = None,
    ) -> tuple[ChatTurnService, ScriptedLLM, Path]:
        database = tmp_path / f"chat-{len(services)}.db"
        settings = Settings(
            internal_token="test-only-agent-token",
            database_path=database,
            checkpoint_path=tmp_path / "checkpoints.db",
            evidence_database_path=tmp_path / "evidence.db",
            canonical_database_path=tmp_path / "canonical.db",
            chat_max_agent_rounds=max_rounds,
            chat_max_tool_calls=max_calls,
        )
        registry = ToolRegistry()

        def echo(request: EchoInput) -> EchoOutput:
            if handler is not None:
                return handler(request)
            return EchoOutput(value=request.value)

        registry.register_tool(
            ToolDefinition[EchoInput, EchoOutput](
                name="normalize_herbs",
                version="test",
                description="只读回显测试工具",
                input_model=EchoInput,
                output_model=EchoOutput,
                required_permissions=frozenset({"herbs:normalize"}),
                handler=echo,
            )
        )
        runtime = ToolRuntime(registry, database)
        llm = ScriptedLLM(responses, gate)
        service = ChatTurnService(runtime, settings=settings, llm=llm)  # type: ignore[arg-type]
        services.append(service)
        return service, llm, database

    yield factory
    for service in services:
        service.close()


def request(turn_id: str) -> ChatTurnCreate:
    return ChatTurnCreate(
        turn_id=turn_id,
        session_id="session-1",
        user_id="user-1",
        message="请分析黄芪",
        history=[{"role": "user", "content": "此前问题"}],
    )


def test_direct_answer(service_factory: Any) -> None:
    service, llm, _ = service_factory([LLMChatResult(content="直接回答")])
    assert service.create(request("direct")).status == "pending"
    assert service.wait_for_idle(2)
    result = service.get("direct")
    assert result.status == "completed"
    assert result.assistant_message == "直接回答"
    assert [event.type for event in result.events] == [
        "node_start",
        "llm_start",
        "assistant_delta",
        "llm_end",
        "node_end",
    ]
    assert result.events[2].delta == "直接回答"
    assert result.events[2].detail == "LLM 内容增量"
    assert llm.messages[0][0]["role"] == "system"


def test_single_tool(service_factory: Any) -> None:
    service, llm, _ = service_factory(
        [tool_call(), LLMChatResult(content="已引用工具结果回答")]
    )
    service.create(request("single"))
    assert service.wait_for_idle(2)
    result = service.get("single")
    assert result.status == "completed"
    assert result.assistant_message == "已引用工具结果回答"
    assert len([event for event in result.events if event.type == "tool_call"]) == 1
    assert llm.messages[1][-1]["role"] == "tool"


def test_single_and_multi_tool_loop(service_factory: Any) -> None:
    responses = [
        tool_call("one", "黄芪"),
        tool_call("two", "甘草"),
        LLMChatResult(content="已根据两轮工具结果回答"),
    ]
    service, llm, _ = service_factory(responses)
    service.create(request("multi"))
    assert service.wait_for_idle(2)
    result = service.get("multi")
    assert result.status == "completed"
    assert len([event for event in result.events if event.type == "tool_call"]) == 2
    assert len([message for message in llm.messages[2] if message["role"] == "tool"]) == 2


@pytest.mark.parametrize(
    ("max_rounds", "max_calls", "expected"), [(1, 12, "轮推理限制"), (8, 1, "工具调用限制")]
)
def test_limits(service_factory: Any, max_rounds: int, max_calls: int, expected: str) -> None:
    first = LLMChatResult(
        tool_calls=[tool_call("one").tool_calls[0], tool_call("two").tool_calls[0]]
    )
    service, _, _ = service_factory(
        [first, tool_call("three")], max_rounds=max_rounds, max_calls=max_calls
    )
    service.create(request(f"limit-{max_rounds}-{max_calls}"))
    assert service.wait_for_idle(2)
    result = service.get(f"limit-{max_rounds}-{max_calls}")
    assert result.status == "completed"
    assert expected in (result.assistant_message or "")
    assert any(event.status == "limit_reached" for event in result.events)


def test_tool_failure_is_returned_to_llm(service_factory: Any) -> None:
    def fail(_request: EchoInput) -> EchoOutput:
        raise RuntimeError("database unavailable token=secret-value")

    service, llm, _ = service_factory(
        [tool_call(), LLMChatResult(content="工具失败，证据不足")], handler=fail
    )
    service.create(request("failure"))
    assert service.wait_for_idle(2)
    result = service.get("failure")
    assert result.status == "completed"
    assert any(event.type == "error" for event in result.events)
    assert "secret-value" not in result.model_dump_json()
    assert "error" in llm.messages[1][-1]["content"]


def test_event_increment_and_auth(service_factory: Any) -> None:
    entered, release = Event(), Event()
    service, _, _ = service_factory([LLMChatResult(content="完成")], gate=(entered, release))
    app.dependency_overrides[get_chat_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert (
                client.post("/internal/v1/chat/turns", json=request("api").model_dump()).status_code
                == 401
            )
            created = client.post(
                "/internal/v1/chat/turns",
                json=request("api").model_dump(),
                headers={"X-Agent-Token": "test-only-agent-token"},
            )
            assert created.status_code == 202
            assert created.json()["status"] == "pending"
            assert entered.wait(2)
            current = client.get(
                "/internal/v1/chat/turns/api",
                headers={"X-Agent-Token": "test-only-agent-token"},
            ).json()
            assert current["status"] == "running"
            assert [event["sequence"] for event in current["events"]] == [1, 2]
            release.set()
            assert service.wait_for_idle(2)
    finally:
        release.set()
        app.dependency_overrides.pop(get_chat_service, None)


def test_sqlite_persistence(service_factory: Any) -> None:
    service, _, database = service_factory([LLMChatResult(content="持久化回答")])
    service.create(request("persisted"))
    assert service.wait_for_idle(2)
    reopened = SQLiteChatRepository(database)
    try:
        result = reopened.get("persisted")
        assert result.assistant_message == "持久化回答"
        assert result.events
    finally:
        reopened.close()


def test_assistant_delta_is_persisted_immediately_and_redacted(service_factory: Any) -> None:
    emitted, release = Event(), Event()
    service, _, _ = service_factory([])
    service._llm = StreamingGateLLM(emitted, release)
    try:
        service.create(request("stream-persist"))
        assert emitted.wait(2)
        current = service.get("stream-persist")
        delta_events = [event for event in current.events if event.type == "assistant_delta"]
        assert current.status == "running"
        assert len(delta_events) == 1
        assert delta_events[0].sequence == 3
        assert delta_events[0].node == "agent"
        assert delta_events[0].status == "streaming"
        assert delta_events[0].detail == "LLM 内容增量"
        assert delta_events[0].delta == "首个 token=[REDACTED]"
        assert "secret-value" not in current.model_dump_json()
    finally:
        release.set()
    assert service.wait_for_idle(2)
    completed = service.get("stream-persist")
    assert [event.delta for event in completed.events if event.type == "assistant_delta"] == [
        "首个 token=[REDACTED]",
        "完成",
    ]
