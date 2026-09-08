from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from typing import Any, Literal, overload

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class LLMToolCallFunction(BaseModel):
    name: str
    arguments: str = "{}"


class LLMToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: LLMToolCallFunction


class LLMChatResult(BaseModel):
    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


class LLMProxyError(Exception):
    """Raised when the LLM proxy call fails."""

    def __init__(self, message: str, is_transient: bool = True) -> None:
        super().__init__(message)
        self.is_transient = is_transient


class LLMProxyClient:
    """Client for the Go LLM proxy, including streaming tool calling."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.llm_proxy_url
        self._stream_url = f"{self._url.rstrip('/')}/stream"
        self._token = settings.internal_token
        self._timeout = httpx.Timeout(settings.llm_timeout_seconds)
        self._stream_mode = settings.llm_stream_mode
        self._max_prompt_length = 32768

    def _rich_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        validated = [LLMMessage.model_validate(message) for message in messages]
        total = sum(len(message.content or "") for message in validated)
        if total > self._max_prompt_length:
            raise LLMProxyError("Message content exceeds limit", is_transient=False)
        payload: dict[str, Any] = {
            "messages": [message.model_dump(exclude_none=True) for message in validated]
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return payload

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Agent-Token": self._token, "Content-Type": "application/json"}

    @overload
    def chat(self, system_prompt: str, user_prompt: str) -> str: ...

    @overload
    def chat(
        self,
        system_prompt: None = None,
        user_prompt: None = None,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMChatResult: ...

    def chat(
        self,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        *,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> str | LLMChatResult:
        """Use legacy prompts or the richer messages/tools contract."""
        legacy = messages is None
        if messages is None:
            if system_prompt is None or user_prompt is None:
                raise ValueError("system_prompt and user_prompt are required for legacy chat")
            payload: dict[str, Any] = {
                "system_prompt": system_prompt[: self._max_prompt_length],
                "user_prompt": user_prompt[: self._max_prompt_length],
            }
        else:
            payload = self._rich_payload(messages, tools, tool_choice)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(self._url, json=payload, headers=self._headers)
                self._raise_for_status(response)
                result = LLMChatResult.model_validate(response.json())
                return result.content or "" if legacy else result
        except httpx.TimeoutException:
            raise LLMProxyError("Request timed out") from None
        except httpx.RequestError:
            logger.warning("LLM proxy is unavailable")
            raise LLMProxyError("Proxy is unavailable") from None
        except httpx.HTTPStatusError as exc:
            raise LLMProxyError(f"Proxy error ({exc.response.status_code})") from None
        except LLMProxyError:
            raise
        except Exception:
            logger.exception("Unexpected error in LLM proxy call")
            raise LLMProxyError("Internal proxy communication error") from None

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMChatResult:
        """Consume the SSE endpoint and return the same aggregate shape as ``chat``.

        Optional mode falls back to non-streaming only before any content has been emitted,
        preventing duplicate user-visible output. Required mode always surfaces stream errors.
        """
        payload = self._rich_payload(messages, tools, tool_choice)
        emitted = False

        def emit(delta: str) -> None:
            nonlocal emitted
            if not delta:
                return
            emitted = True
            if on_delta is not None:
                on_delta(delta)

        try:
            return self._stream_chat_once(payload, emit)
        except LLMProxyError as exc:
            if self._stream_mode != "optional" or emitted or not exc.is_transient:
                raise
            logger.warning("Streaming LLM proxy unavailable; using non-streaming fallback")
            result = self.chat(messages=messages, tools=tools, tool_choice=tool_choice)
            if result.content:
                emit(result.content)
            return result
        except Exception:
            logger.warning("Unexpected streaming LLM proxy failure")
            raise LLMProxyError(
                "Internal streaming proxy communication error", is_transient=False
            ) from None

    def _stream_chat_once(
        self, payload: dict[str, Any], on_delta: Callable[[str], None]
    ) -> LLMChatResult:
        content_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        done = False
        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream(
                    "POST", self._stream_url, json=payload, headers=self._headers
                ) as response:
                    self._raise_for_status(response)
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/event-stream" not in content_type:
                        raise LLMProxyError("Streaming is not supported by proxy")
                    for event_name, data in self._iter_sse(response.iter_lines()):
                        if data == "[DONE]" or event_name == "done":
                            done = True
                            break
                        try:
                            value = json.loads(data)
                        except json.JSONDecodeError:
                            raise LLMProxyError(
                                "Invalid streaming response", is_transient=False
                            ) from None
                        if not isinstance(value, dict):
                            raise LLMProxyError("Invalid streaming response", is_transient=False)
                        kind = event_name or str(value.get("type", ""))
                        if kind == "delta":
                            delta = value.get("content", "")
                            if not isinstance(delta, str):
                                raise LLMProxyError(
                                    "Invalid streaming response", is_transient=False
                                )
                            content_parts.append(delta)
                            on_delta(delta)
                        elif kind == "tool_call_delta":
                            self._merge_tool_call_delta(calls, value)
                        elif kind == "error":
                            raise LLMProxyError("Streaming proxy returned an error")
                    if not done:
                        raise LLMProxyError("Streaming response ended before done")
        except httpx.TimeoutException:
            raise LLMProxyError("Streaming request timed out") from None
        except httpx.RequestError:
            logger.warning("Streaming LLM proxy is unavailable")
            raise LLMProxyError("Streaming proxy is unavailable") from None
        except httpx.HTTPStatusError as exc:
            raise LLMProxyError(f"Streaming proxy error ({exc.response.status_code})") from None

        tool_calls: list[LLMToolCall] = []
        for _, call in sorted(calls.items()):
            if not call["id"] or not call["name"]:
                raise LLMProxyError("Incomplete tool call stream", is_transient=False)
            tool_calls.append(
                LLMToolCall(
                    id=call["id"],
                    function=LLMToolCallFunction(
                        name=call["name"], arguments=call["arguments"] or "{}"
                    ),
                )
            )
        return LLMChatResult(content="".join(content_parts) or None, tool_calls=tool_calls)

    @staticmethod
    def _iter_sse(lines: Iterator[str]) -> Iterator[tuple[str, str]]:
        event_name = ""
        data_lines: list[str] = []
        for raw_line in lines:
            line = raw_line.rstrip("\r")
            if not line:
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                event_name, data_lines = "", []
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "event":
                event_name = value
            elif field == "data":
                data_lines.append(value)
        if data_lines:
            yield event_name, "\n".join(data_lines)

    @staticmethod
    def _merge_tool_call_delta(calls: dict[int, dict[str, str]], value: dict[str, Any]) -> None:
        index = value.get("index")
        if not isinstance(index, int) or index < 0:
            raise LLMProxyError("Invalid tool call stream", is_transient=False)
        function = value.get("function")
        nested = function if isinstance(function, dict) else {}
        call = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        for key in ("id", "name", "arguments"):
            fragment = nested.get(key) if key in nested else value.get(key)
            if fragment is not None:
                if not isinstance(fragment, str):
                    raise LLMProxyError("Invalid tool call stream", is_transient=False)
                call[key] += fragment

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            logger.error("LLM proxy authentication failed")
            raise LLMProxyError("Authentication failed", is_transient=False)
        if response.status_code in {400, 403, 422}:
            raise LLMProxyError(
                f"Proxy rejected request ({response.status_code})", is_transient=False
            )
        response.raise_for_status()
