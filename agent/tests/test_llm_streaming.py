from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.services.llm_proxy import LLMProxyClient, LLMProxyError


def settings(tmp_path: Path, *, stream_mode: str = "required") -> Settings:
    return Settings(
        internal_token="test-only-agent-token",
        database_path=tmp_path / "runs.db",
        checkpoint_path=tmp_path / "checkpoints.db",
        evidence_database_path=tmp_path / "evidence.db",
        canonical_database_path=tmp_path / "canonical.db",
        llm_proxy_url="http://go/internal/v1/llm/chat",
        llm_stream_mode=stream_mode,
    )


def client_for(body: str, tmp_path: Path, *, stream_mode: str = "required") -> LLMProxyClient:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream; charset=utf-8"},
        content=body,
        request=httpx.Request("POST", "http://go/internal/v1/llm/chat/stream"),
    )
    transport = httpx.MockTransport(lambda _request: response)
    real_client = httpx.Client(transport=transport)
    proxy = LLMProxyClient(settings(tmp_path, stream_mode=stream_mode))
    proxy._test_http_client = real_client  # type: ignore[attr-defined]
    return proxy


def run_with_client(
    proxy: LLMProxyClient,
    callback: Callable[[str], None] | None = None,
) -> Any:
    real_client = proxy._test_http_client  # type: ignore[attr-defined]
    with patch("app.services.llm_proxy.httpx.Client", return_value=real_client):
        return proxy.stream_chat(
            messages=[{"role": "user", "content": "hello"}], on_delta=callback
        )


def test_stream_chat_aggregates_text_deltas_and_multiline_sse(tmp_path: Path) -> None:
    proxy = client_for(
        'event: delta\ndata: {"content":"你"}\n\n'
        'event: delta\ndata: {"content":\ndata: "好"}\n\n'
        "data: [DONE]\n\n",
        tmp_path,
    )
    deltas: list[str] = []

    result = run_with_client(proxy, deltas.append)

    assert result.content == "你好"
    assert deltas == ["你", "好"]


def test_stream_chat_aggregates_fragmented_multiple_tool_calls(tmp_path: Path) -> None:
    proxy = client_for(
        'event: tool_call_delta\ndata: {"index":1,"id":"call-b","name":"search_"}\n\n'
        'event: tool_call_delta\ndata: {"index":0,"id":"call-a","function":'
        '{"name":"normalize_herbs","arguments":"{\\"value\\":"}}\n\n'
        'event: tool_call_delta\ndata: {"index":1,"name":"literature",'
        '"arguments":"{\\"query\\":\\"黄芪\\"}"}\n\n'
        'event: tool_call_delta\ndata: {"index":0,"arguments":"\\"黄芪\\"}"}\n\n'
        "event: done\ndata: {}\n\n",
        tmp_path,
    )

    result = run_with_client(proxy)

    assert [call.id for call in result.tool_calls] == ["call-a", "call-b"]
    assert result.tool_calls[0].function.name == "normalize_herbs"
    assert result.tool_calls[0].function.arguments == '{"value":"黄芪"}'
    assert result.tool_calls[1].function.name == "search_literature"
    assert result.tool_calls[1].function.arguments == '{"query":"黄芪"}'


def test_stream_chat_error_is_safe_and_required_does_not_fallback(tmp_path: Path) -> None:
    proxy = client_for(
        'event: error\ndata: {"message":"token=do-not-leak"}\n\n', tmp_path
    )

    with pytest.raises(LLMProxyError) as exc:
        run_with_client(proxy)

    assert str(exc.value) == "Streaming proxy returned an error"
    assert "do-not-leak" not in str(exc.value)


def test_stream_chat_optional_falls_back_once(tmp_path: Path) -> None:
    stream_response = httpx.Response(
        404,
        request=httpx.Request("POST", "http://go/internal/v1/llm/chat/stream"),
    )
    chat_response = httpx.Response(
        200,
        json={"content": "fallback answer"},
        request=httpx.Request("POST", "http://go/internal/v1/llm/chat"),
    )
    clients = [
        httpx.Client(transport=httpx.MockTransport(lambda _request: stream_response)),
        httpx.Client(transport=httpx.MockTransport(lambda _request: chat_response)),
    ]
    proxy = LLMProxyClient(settings(tmp_path, stream_mode="optional"))
    deltas: list[str] = []

    with patch("app.services.llm_proxy.httpx.Client", side_effect=clients):
        result = proxy.stream_chat(
            messages=[{"role": "user", "content": "hello"}], on_delta=deltas.append
        )

    assert result.content == "fallback answer"
    assert deltas == ["fallback answer"]


def test_stream_chat_does_not_fallback_after_delta(tmp_path: Path) -> None:
    proxy = client_for(
        'event: delta\ndata: {"content":"partial"}\n\n'
        'event: error\ndata: {"message":"failed"}\n\n',
        tmp_path,
        stream_mode="optional",
    )
    deltas: list[str] = []

    with pytest.raises(LLMProxyError):
        run_with_client(proxy, deltas.append)

    assert deltas == ["partial"]
