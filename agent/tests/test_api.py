import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.run_service import run_service

client = TestClient(app)
AUTH_HEADERS = {"X-Agent-Token": "test-only-agent-token"}
RUN_PAYLOAD = {
    "run_id": "run-001",
    "user_id": 1001,
    "trace_id": "trace-001",
    "herbs": ["黄芪", "当归"],
    "research_goal": None,
}


@pytest.fixture(autouse=True)
def reset_store() -> Iterator[None]:
    run_service.clear()
    yield
    run_service.clear()


def test_health_is_public() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "service": "medical-agent",
        "status": "ok",
        "version": get_settings().service_version,
    }


def test_create_run_returns_running_then_completes() -> None:
    response = client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=AUTH_HEADERS)

    assert response.status_code == 201
    body = response.json()
    assert body["run_id"] == RUN_PAYLOAD["run_id"]
    assert body["herbs"] == RUN_PAYLOAD["herbs"]
    assert body["status"] == "running"
    assert body["updated_at"] >= body["created_at"]
    assert run_service.wait_for_idle(timeout=30)
    completed = client.get("/internal/v1/runs/run-001", headers=AUTH_HEADERS).json()
    assert completed["status"] == "completed"
    analysis = completed["analysis_result"]
    assert analysis["schema_version"] == "2.0"
    assert analysis["normalized_herbs"] == ["黄芪", "当归"]
    assert analysis["summary"]["compound_count"] == 2
    assert len(analysis["evidence"]) >= 2
    evidence_ids = {item["evidence_id"] for item in analysis["evidence"]}
    assert all(compound["evidence_ids"] for compound in analysis["compounds"])
    assert all(set(claim["evidence_ids"]) <= evidence_ids for claim in analysis["claims"])
    assert analysis["capabilities"]["literature_retrieval"]["status"] == "available"


def test_duplicate_run_returns_conflict() -> None:
    client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=AUTH_HEADERS)
    response = client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=AUTH_HEADERS)
    assert response.status_code == 409
    assert response.json() == {"detail": "Run 'run-001' already exists"}


def test_get_completed_run() -> None:
    client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=AUTH_HEADERS)
    assert run_service.wait_for_idle(timeout=30)
    fetched = client.get("/internal/v1/runs/run-001", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"
    assert fetched.json()["analysis_result"] is not None


@pytest.mark.parametrize("method", ["get", "delete"])
def test_run_not_found(method: str) -> None:
    response = getattr(client, method)("/internal/v1/runs/missing", headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert response.json() == {"detail": "Run 'missing' not found"}


@pytest.mark.parametrize(
    "payload",
    [
        {**RUN_PAYLOAD, "herbs": []},
        {key: value for key, value in RUN_PAYLOAD.items() if key != "run_id"},
        {**RUN_PAYLOAD, "unexpected_field": True},
    ],
)
def test_create_run_validation_failure(payload: dict[str, object]) -> None:
    response = client.post("/internal/v1/runs", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 422
    assert response.json() == {"detail": "Request validation failed"}


@pytest.mark.parametrize("headers", [None, {"X-Agent-Token": "wrong-token"}])
def test_internal_route_rejects_invalid_authentication(
    headers: dict[str, str] | None,
) -> None:
    response = client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing agent token"}


def test_startup_fails_when_internal_token_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AGENT_INTERNAL_TOKEN", raising=False)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "internal_token" in result.stderr


def test_evidence_endpoints_require_auth_and_use_runtime() -> None:
    assert client.get("/internal/v1/evidence/quality").status_code == 401
    quality = client.get("/internal/v1/evidence/quality", headers=AUTH_HEADERS)
    assert quality.status_code == 200
    assert (
        quality.json()["source_sha256"]
        == "040e504414beaa2fca3c4b8c49c4007bc6a4ca857cf8d105c5c723f4b02fd5fd"
    )

    assert client.post("/internal/v1/evidence/search", json={}).status_code == 401
    searched = client.post(
        "/internal/v1/evidence/search",
        headers=AUTH_HEADERS,
        json={"herbs": ["甘草"], "top_k": 2},
    )
    assert searched.status_code == 200
    assert searched.json()["hits"]
    assert searched.json()["hits"][0]["matched_fields"] == ["herbs"]


def test_proposal_endpoint_auth_not_found_conflict_and_success() -> None:
    assert client.get("/internal/v1/runs/missing/proposal").status_code == 401
    missing = client.get("/internal/v1/runs/missing/proposal", headers=AUTH_HEADERS)
    assert missing.status_code == 404

    created = client.post("/internal/v1/runs", json=RUN_PAYLOAD, headers=AUTH_HEADERS)
    assert created.status_code == 201
    pending = client.get("/internal/v1/runs/run-001/proposal", headers=AUTH_HEADERS)
    assert pending.status_code == 409

    assert run_service.wait_for_idle(timeout=30)
    response = client.get("/internal/v1/runs/run-001/proposal", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["condition_matrix"]
    assert body["review"]["checked_rules"]
