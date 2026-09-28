from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from app.core.config import Settings
from app.models.run import LLMStatus
from app.services.agent.analysis import AnalysisService
from app.services.agent.workflow import LangGraphAnalysisWorkflow, WorkflowState
from app.services.infrastructure.llm_proxy import LLMChatResult, LLMProxyClient, LLMProxyError


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        internal_token="test-token-for-agent",
        testing=True,
        llm_proxy_url="http://test/chat",
        llm_timeout_seconds=10.0,
        llm_stream_mode="optional",
        llm_mode="optional",
    )


def test_llm_proxy_client_success(mock_settings: Any) -> None:
    client = LLMProxyClient(mock_settings)
    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"content": "Summary text"}

        res = client.chat("sys", "user")
        assert res == "Summary text"
        mock_post.assert_called_once()


def test_llm_proxy_client_structured_tool_call(mock_settings: Any) -> None:
    client = LLMProxyClient(mock_settings)
    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "search_toxicology_knowledge",
                        "arguments": '{"query":"黄芪"}',
                    },
                }
            ],
        }

        result = client.chat(
            messages=[{"role": "user", "content": "检索黄芪"}],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "search_toxicology_knowledge"},
                }
            ],
            tool_choice="auto",
        )

        assert isinstance(result, LLMChatResult)
        assert result.tool_calls[0].function.name == "search_toxicology_knowledge"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["messages"][0]["role"] == "user"
        assert payload["tool_choice"] == "auto"


def test_llm_proxy_client_auth_failure(mock_settings: Any) -> None:
    client = LLMProxyClient(mock_settings)
    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value.status_code = 401

        with pytest.raises(LLMProxyError) as exc:
            client.chat("sys", "user")
        assert "Authentication failed" in str(exc.value)


@patch("app.services.agent.workflow.get_settings")
def test_workflow_llm_disabled(
    mock_get_settings: Any, mock_settings: Any
) -> None:
    mock_settings.llm_mode = "disabled"
    mock_get_settings.return_value = mock_settings

    analysis = MagicMock(spec=AnalysisService)
    analysis.finalize.return_value = MagicMock()

    workflow = LangGraphAnalysisWorkflow(analysis, llm=MagicMock())
    state = WorkflowState(
        herbs=["黄芪"],
        normalized_herbs=["黄芪"],
        compounds=[],
        evidence=[],
        unresolved_herbs=[],
        online_failures=0,
        proposal={},
        proposal_review={},
        steps=[],
    )
    config = RunnableConfig(configurable={"thread_id": "test-run"})

    workflow._finalize(state, config)
    analysis.finalize.assert_called_once()
    kwargs = analysis.finalize.call_args.kwargs
    assert kwargs["llm_status"] == LLMStatus.DISABLED
    assert kwargs["llm_summary"] is None


@patch("app.services.agent.workflow.get_settings")
def test_workflow_llm_success(
    mock_get_settings: Any, mock_settings: Any
) -> None:
    mock_settings.llm_mode = "optional"
    mock_get_settings.return_value = mock_settings

    analysis = MagicMock(spec=AnalysisService)
    analysis.finalize.return_value = MagicMock()

    mock_llm = MagicMock(spec=LLMProxyClient)
    mock_llm.chat.return_value = "Success Summary"

    workflow = LangGraphAnalysisWorkflow(analysis, llm=mock_llm)
    state = WorkflowState(
        herbs=["黄芪"],
        normalized_herbs=["黄芪"],
        compounds=[],
        evidence=[],
        unresolved_herbs=[],
        online_failures=0,
        proposal={},
        proposal_review={},
        steps=[],
    )
    config = RunnableConfig(configurable={"thread_id": "test-run"})

    workflow._finalize(state, config)
    analysis.finalize.assert_called_once()
    kwargs = analysis.finalize.call_args.kwargs
    assert kwargs["llm_status"] == LLMStatus.GENERATED
    assert kwargs["llm_summary"] == "Success Summary"


@patch("app.services.agent.workflow.get_settings")
def test_workflow_llm_optional_fallback(
    mock_get_settings: Any, mock_settings: Any
) -> None:
    mock_settings.llm_mode = "optional"
    mock_get_settings.return_value = mock_settings

    analysis = MagicMock(spec=AnalysisService)
    analysis.finalize.return_value = MagicMock()

    mock_llm = MagicMock(spec=LLMProxyClient)
    mock_llm.chat.side_effect = LLMProxyError("Fail")

    workflow = LangGraphAnalysisWorkflow(analysis, llm=mock_llm)
    state = WorkflowState(
        herbs=["黄芪"],
        normalized_herbs=["黄芪"],
        compounds=[],
        evidence=[],
        unresolved_herbs=[],
        online_failures=0,
        proposal={},
        proposal_review={},
        steps=[],
    )
    config = RunnableConfig(configurable={"thread_id": "test-run"})

    workflow._finalize(state, config)
    analysis.finalize.assert_called_once()
    kwargs = analysis.finalize.call_args.kwargs
    assert kwargs["llm_status"] == LLMStatus.DEGRADED
    assert kwargs["llm_summary"] is None


@patch("app.services.agent.workflow.get_settings")
def test_workflow_llm_required_failure(
    mock_get_settings: Any, mock_settings: Any
) -> None:
    mock_settings.llm_mode = "required"
    mock_get_settings.return_value = mock_settings

    analysis = MagicMock(spec=AnalysisService)

    mock_llm = MagicMock(spec=LLMProxyClient)
    mock_llm.chat.side_effect = LLMProxyError("Fail")

    workflow = LangGraphAnalysisWorkflow(analysis, llm=mock_llm)
    state = WorkflowState(
        herbs=["黄芪"],
        normalized_herbs=["黄芪"],
        compounds=[],
        evidence=[],
        unresolved_herbs=[],
        online_failures=0,
        proposal={},
        proposal_review={},
        steps=[],
    )
    config = RunnableConfig(configurable={"thread_id": "test-run"})

    with pytest.raises(LLMProxyError):
        workflow._finalize(state, config)
