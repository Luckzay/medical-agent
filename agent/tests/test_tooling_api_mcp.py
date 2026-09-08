from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import get_tool_runtime
from app.core.config import Settings
from app.main import app
from app.models.tooling import ToolExecutionContext
from app.services.analysis_service import AnalysisService
from app.services.builtin_tools import INTERNAL_TOOL_PERMISSIONS, build_tool_registry
from app.services.tool_runtime import ToolRuntime

TOKEN = "test-only-agent-token"
HEADERS = {"X-Agent-Token": TOKEN}
MCP_HEADERS = {**HEADERS, "Accept": "application/json, text/event-stream"}


def rpc(method: str, request_id: int, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def test_internal_tooling_endpoints_require_auth_and_return_audits(tmp_path: Any) -> None:
    settings = Settings(
        internal_token=TOKEN,
        offline_mode=True,
        database_path=tmp_path / "api.db",
        checkpoint_path=tmp_path / "checkpoint.db",
    )
    runtime = ToolRuntime(build_tool_registry(AnalysisService(settings)), settings.database_path)
    runtime.execute(
        "normalize_herbs",
        {"herbs": ["黄芪"]},
        ToolExecutionContext(
            run_id="api-audit", node="normalize", permissions=INTERNAL_TOOL_PERMISSIONS
        ),
    )
    app.dependency_overrides[get_tool_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            assert client.get("/internal/v1/tools").status_code == 401
            tools = client.get("/internal/v1/tools", headers=HEADERS)
            skills = client.get("/internal/v1/skills", headers=HEADERS)
            audits = client.get("/internal/v1/runs/api-audit/tool-audits", headers=HEADERS)
        assert tools.status_code == 200
        assert {item["name"] for item in tools.json()} == {
            "normalize_herbs",
            "discover_compounds",
            "calculate_descriptors",
            "score_supramolecular_candidate",
            "search_literature",
            "search_medical_knowledge",
            "generate_experiment_proposal",
            "review_experiment_proposal",
        }
        assert len(skills.json()) == 5
        assert audits.json()[0]["tool_name"] == "normalize_herbs"
        assert "handler" not in tools.text
    finally:
        app.dependency_overrides.pop(get_tool_runtime, None)
        runtime.close()


def test_mcp_real_initialize_list_and_call_protocol() -> None:
    with TestClient(app) as client:
        assert client.post("/mcp/", json=rpc("tools/list", 0, {})).status_code == 401
        initialized = client.post(
            "/mcp/",
            headers=MCP_HEADERS,
            json=rpc(
                "initialize",
                1,
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            ),
        )
        listed = client.post("/mcp/", headers=MCP_HEADERS, json=rpc("tools/list", 2, {}))
        called = client.post(
            "/mcp/",
            headers=MCP_HEADERS,
            json=rpc(
                "tools/call",
                3,
                {
                    "name": "normalize_herbs",
                    "arguments": {"herbs": [" 黃耆 ", "黄芪"], "run_id": "protocol"},
                },
            ),
        )
        searched = client.post(
            "/mcp/",
            headers=MCP_HEADERS,
            json=rpc(
                "tools/call",
                4,
                {
                    "name": "search_literature",
                    "arguments": {"herbs": ["甘草"], "top_k": 1, "run_id": "evidence"},
                },
            ),
        )
        generated = client.post(
            "/mcp/",
            headers=MCP_HEADERS,
            json=rpc(
                "tools/call",
                5,
                {
                    "name": "generate_experiment_proposal",
                    "arguments": {
                        "compounds": [
                            {
                                "compound_id": "fixture",
                                "name": "Fixture",
                                "herb": "当归",
                                "smiles": "CO",
                                "pubchem_cid": None,
                                "descriptors": {
                                    "molecular_weight": None,
                                    "logp": None,
                                    "tpsa": None,
                                    "hbd": None,
                                    "hba": None,
                                },
                                "candidate_score": {
                                    "rules": [],
                                    "total_score": 7,
                                    "candidate_threshold": 6,
                                    "is_candidate": True,
                                },
                                "evidence_ids": ["seed:fixture"],
                            }
                        ],
                        "claims": [],
                        "evidence": [
                            {
                                "evidence_id": "seed:fixture",
                                "source": "fixture",
                                "source_type": "local_seed",
                                "reference": "seed://fixture",
                                "retrieved_at": None,
                                "title": None,
                                "link": None,
                                "year": None,
                                "source_row": None,
                                "matched_fields": [],
                                "score": None,
                                "conditions": None,
                            }
                        ],
                        "max_conditions": 1,
                        "run_id": "proposal",
                    },
                },
            ),
        )
        proposal = generated.json()["result"]["structuredContent"]
        reviewed = client.post(
            "/mcp/",
            headers=MCP_HEADERS,
            json=rpc(
                "tools/call",
                6,
                {
                    "name": "review_experiment_proposal",
                    "arguments": {
                        "proposal": proposal,
                        "available_evidence_ids": ["seed:fixture"],
                        "run_id": "review",
                    },
                },
            ),
        )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["version"] == "0.7.0"
    tools = {item["name"] for item in listed.json()["result"]["tools"]}
    assert len(tools) == 7
    assert {"generate_experiment_proposal", "review_experiment_proposal"} <= tools
    assert called.json()["result"]["structuredContent"] == {"normalized_herbs": ["黄芪"]}
    assert searched.status_code == 200
    assert searched.json()["result"]["structuredContent"]["hits"]

    assert generated.status_code == 200
    assert proposal["condition_matrix"][0]["source_type"] == "exploratory_default"
    assert reviewed.status_code == 200
    assert reviewed.json()["result"]["structuredContent"]["status"] == "needs_revision"
