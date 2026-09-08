from __future__ import annotations

import json
import re
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from functools import partial
from threading import RLock
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings, get_settings
from app.models.chat import ChatEvent, ChatTurnCreate, ChatTurnResponse
from app.models.tooling import ToolExecutionContext
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS
from app.services.chat_repository import (
    ChatTurnNotFoundError,
    DuplicateChatTurnError,
    SQLiteChatRepository,
)
from app.services.llm_proxy import LLMProxyClient
from app.services.tool_runtime import ToolRuntime

SYSTEM_PROMPT = """你是医学科研辅助智能体。你必须根据问题自主决定是否调用工具以及调用哪个工具。
必须引用工具结果中的来源、证据标识或关键数据；不得伪造文献、数据、结论或工具结果。
当工具结果不足、冲突或失败时，明确说明不确定性和证据缺口。你的回答仅用于科研辅助，
不得替代临床诊断或治疗决策。"""

CHAT_TOOL_ALLOWLIST = frozenset(
    {
        "normalize_herbs",
        "discover_compounds",
        "calculate_descriptors",
        "score_supramolecular_candidate",
        "search_literature",
        "search_medical_knowledge",
        "generate_experiment_proposal",
        "review_experiment_proposal",
    }
)
_SENSITIVE_KEY = re.compile(r"token|secret|password|api[_-]?key|authorization|cookie", re.I)
_SENSITIVE_TEXT = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_SENSITIVE_ASSIGNMENT = re.compile(
    r'(?i)(["\']?(?:token|secret|password|api[_-]?key|authorization)["\']?\s*[:=]\s*)'
    r'(["\']?)[^\s,"\'}]+\2'
)


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    rounds: int
    tool_calls: int
    final_message: str | None
    stop_reason: str | None


class ChatTurnService:
    """Asynchronous, durable dynamic ReAct chat service backed by LangGraph."""

    def __init__(
        self,
        runtime: ToolRuntime,
        *,
        settings: Settings | None = None,
        repository: SQLiteChatRepository | None = None,
        llm: LLMProxyClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._runtime = runtime
        self._repository = repository or SQLiteChatRepository(self._settings.database_path)
        self._llm = llm or LLMProxyClient(self._settings)
        self._lock = RLock()
        self._executor: ThreadPoolExecutor | None = None
        self._futures: set[Future[None]] = set()
        self._scheduled: set[str] = set()
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self._after_agent, {"tools": "tools", "end": END})
        graph.add_conditional_edges("tools", self._after_tools, {"agent": "agent", "end": END})
        return graph.compile()

    def _tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for metadata in self._runtime.registry.list_tools():
            name = str(metadata["name"])
            if name not in CHAT_TOOL_ALLOWLIST:
                continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": metadata["description"],
                        "parameters": metadata["input_schema"],
                    },
                }
            )
        return schemas

    def _event(
        self,
        event_type: Literal[
            "node_start",
            "node_end",
            "llm_start",
            "llm_end",
            "assistant_delta",
            "tool_call",
            "tool_result",
            "error",
        ],
        node: str,
        status: str,
        detail: str,
        *,
        delta: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        input_data: Any | None = None,
        output_data: Any | None = None,
    ) -> None:
        turn_id = self._current_turn_id()
        event = ChatEvent(
            sequence=self._repository.next_sequence(turn_id),
            type=event_type,
            node=node,
            status=status,
            detail=self._safe_text(detail, 500),
            delta=(
                self._safe_text(delta, self._settings.chat_event_payload_chars)
                if delta is not None
                else None
            ),
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            input=self._safe_payload(input_data),
            output=self._safe_payload(output_data),
            created_at=datetime.now(UTC),
        )
        self._repository.append_event(turn_id, event)

    _thread_local_turn: dict[int, str] = {}

    def _current_turn_id(self) -> str:
        import threading

        turn_id = self._thread_local_turn.get(threading.get_ident())
        if turn_id is None:
            raise RuntimeError("chat turn context is unavailable")
        return turn_id

    def _safe_text(self, text: str, limit: int) -> str:
        text = _SENSITIVE_TEXT.sub(r"\1[REDACTED]", text.replace("\x00", ""))
        return _SENSITIVE_ASSIGNMENT.sub(r"\1[REDACTED]", text)[:limit]

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, str):
            return self._safe_text(value, self._settings.chat_event_payload_chars)
        return value

    def _safe_payload(self, value: Any | None) -> Any | None:
        if value is None:
            return None
        redacted = self._redact(value)
        encoded = json.dumps(redacted, ensure_ascii=False, default=str)
        limit = self._settings.chat_event_payload_chars
        if len(encoded) <= limit:
            return redacted
        return encoded[:limit] + "…[truncated]"

    def _agent_node(self, state: AgentState) -> AgentState:
        self._event("node_start", "agent", "running", "智能体节点开始")
        if state["rounds"] >= self._settings.chat_max_agent_rounds:
            message = (
                f"已达到最多 {self._settings.chat_max_agent_rounds} 轮推理限制，无法继续调用工具。"
            )
            self._event("node_end", "agent", "limit_reached", message)
            return {**state, "final_message": message, "stop_reason": "round_limit"}
        self._event("llm_start", "agent", "running", "开始请求 LLM")

        def persist_delta(delta: str) -> None:
            self._event(
                "assistant_delta",
                "agent",
                "streaming",
                "LLM 内容增量",
                delta=delta,
            )

        response = self._llm.stream_chat(
            messages=state["messages"],
            tools=self._tool_schemas(),
            tool_choice="auto",
            on_delta=persist_delta,
        )
        tool_calls = [call.model_dump(mode="json") for call in response.tool_calls]
        assistant = {"role": "assistant", "content": response.content, "tool_calls": tool_calls}
        messages = [*state["messages"], assistant]
        self._event(
            "llm_end",
            "agent",
            "completed",
            "LLM 返回工具调用" if tool_calls else "LLM 返回最终回答",
            output_data={"content": response.content, "tool_calls": tool_calls},
        )
        self._event("node_end", "agent", "completed", "智能体节点结束")
        return {
            **state,
            "messages": messages,
            "rounds": state["rounds"] + 1,
            "final_message": response.content if not tool_calls else None,
        }

    @staticmethod
    def _after_agent(state: AgentState) -> str:
        if state["stop_reason"] or state["final_message"] is not None:
            return "end"
        last = state["messages"][-1]
        return "tools" if last.get("tool_calls") else "end"

    def _tools_node(self, state: AgentState) -> AgentState:
        self._event("node_start", "tools", "running", "工具节点开始")
        messages = list(state["messages"])
        count = state["tool_calls"]
        for call in messages[-1].get("tool_calls", []):
            if count >= self._settings.chat_max_tool_calls:
                message = (
                    f"已达到最多 {self._settings.chat_max_tool_calls} 次工具调用限制，停止执行。"
                )
                self._event("error", "tools", "limit_reached", message)
                self._event("node_end", "tools", "limit_reached", message)
                return {
                    **state,
                    "messages": messages,
                    "tool_calls": count,
                    "final_message": message,
                    "stop_reason": "tool_limit",
                }
            function = call.get("function", {})
            name, call_id = str(function.get("name", "")), str(call.get("id", ""))
            try:
                arguments = json.loads(str(function.get("arguments", "{}")))
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments must be an object")
                if name not in CHAT_TOOL_ALLOWLIST:
                    raise ValueError("tool is not available to chat")
                self._event(
                    "tool_call",
                    "tools",
                    "running",
                    "执行只读/计算工具",
                    tool_name=name,
                    tool_call_id=call_id,
                    input_data=arguments,
                )
                output = self._runtime.execute(
                    name,
                    arguments,
                    ToolExecutionContext(
                        run_id=self._current_turn_id(),
                        node="chat:tools",
                        permissions=INTERNAL_TOOL_PERMISSIONS,
                    ),
                ).model_dump(mode="json")
                self._event(
                    "tool_result",
                    "tools",
                    "completed",
                    "工具执行成功",
                    tool_name=name,
                    tool_call_id=call_id,
                    output_data=output,
                )
                content = json.dumps(output, ensure_ascii=False)
            except Exception as exc:
                safe_error = self._safe_text(str(exc) or type(exc).__name__, 300)
                self._event(
                    "error",
                    "tools",
                    "failed",
                    safe_error,
                    tool_name=name or None,
                    tool_call_id=call_id or None,
                )
                self._event(
                    "tool_result",
                    "tools",
                    "failed",
                    "工具执行失败",
                    tool_name=name or None,
                    tool_call_id=call_id or None,
                    output_data={"error": safe_error},
                )
                content = json.dumps({"error": safe_error}, ensure_ascii=False)
            messages.append(
                {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}
            )
            count += 1
        self._event("node_end", "tools", "completed", "工具节点结束")
        return {**state, "messages": messages, "tool_calls": count}

    @staticmethod
    def _after_tools(state: AgentState) -> str:
        return "end" if state["stop_reason"] else "agent"

    def create(self, request: ChatTurnCreate) -> ChatTurnResponse:
        response = self._repository.create(request)
        self._submit(request.turn_id)
        return response

    def get(self, turn_id: str) -> ChatTurnResponse:
        return self._repository.get(turn_id)

    def _ensure_executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._settings.worker_count, thread_name_prefix="agent-chat"
                )
            return self._executor

    def _submit(self, turn_id: str) -> None:
        with self._lock:
            if turn_id in self._scheduled:
                return
            self._scheduled.add(turn_id)
            future = self._ensure_executor().submit(self._execute, turn_id)
            self._futures.add(future)
            future.add_done_callback(partial(self._done, turn_id))

    def _done(self, turn_id: str, future: Future[None]) -> None:
        with self._lock:
            self._scheduled.discard(turn_id)
            self._futures.discard(future)

    def _execute(self, turn_id: str) -> None:
        import threading

        self._thread_local_turn[threading.get_ident()] = turn_id
        try:
            request = self._repository.load_request(turn_id)
            self._repository.set_status(turn_id, "running")
            messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(item.model_dump() for item in request.history)
            messages.append({"role": "user", "content": request.message})
            result = cast(
                AgentState,
                self._graph.invoke(
                    AgentState(
                        messages=messages,
                        rounds=0,
                        tool_calls=0,
                        final_message=None,
                        stop_reason=None,
                    )
                ),
            )
            final_message = result["final_message"] or "当前无法形成可靠回答，请补充信息后重试。"
            self._repository.set_status(turn_id, "completed", assistant_message=final_message)
        except Exception as exc:
            safe_error = self._safe_text(str(exc) or type(exc).__name__, 300)
            try:
                self._event("error", "worker", "failed", safe_error)
                self._repository.set_status(turn_id, "failed", error_message=safe_error)
            except Exception:
                pass
        finally:
            self._thread_local_turn.pop(threading.get_ident(), None)

    def recover_pending_tasks(self) -> None:
        for turn_id in self._repository.list_recoverable():
            self._submit(turn_id)

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        with self._lock:
            futures = set(self._futures)
        if not futures:
            return True
        _done, pending = wait(futures, timeout=timeout)
        return not pending

    def shutdown(self, wait_for_workers: bool = True) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=wait_for_workers, cancel_futures=False)

    def close(self) -> None:
        self.shutdown()
        self._repository.close()


__all__ = [
    "ChatTurnNotFoundError",
    "ChatTurnService",
    "DuplicateChatTurnError",
]
