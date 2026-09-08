from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import management
from app.main import app
from app.services.knowledge_repository import SQLiteCanonicalRepository

AUTH = {
    "X-Agent-Token": "test-only-agent-token",
    "X-Tenant-ID": "tenant",
    "X-Project-ID": "project",
    "X-Agent-Permissions": "documents:write,indexes:manage",
}


def test_management_auth_scope_idempotency_lifecycle_and_degraded_mode(tmp_path: Path) -> None:
    management._repository = SQLiteCanonicalRepository(tmp_path / "api.db")
    client = TestClient(app)
    payload = {
        "logical_source": "memory:api",
        "media_type": "text/plain",
        "content_text": "canonical API content",
    }
    assert client.post("/internal/v1/documents/ingestions", json=payload).status_code == 401
    assert (
        client.post("/internal/v1/documents/ingestions", json=payload, headers=AUTH).status_code
        == 422
    )
    denied = {**AUTH, "X-Agent-Permissions": "indexes:manage", "Idempotency-Key": "request-0001"}
    assert (
        client.post("/internal/v1/documents/ingestions", json=payload, headers=denied).status_code
        == 403
    )
    headers = {**AUTH, "Idempotency-Key": "request-0001"}
    created = client.post("/internal/v1/documents/ingestions", json=payload, headers=headers)
    assert created.status_code == 202
    duplicate = client.post("/internal/v1/documents/ingestions", json=payload, headers=headers)
    assert duplicate.json()["job_id"] == created.json()["job_id"]
    status = client.get(f"/internal/v1/ingestions/{created.json()['job_id']}", headers=AUTH)
    assert status.status_code == 200 and status.json()["stage"] == "ready"
    document_id = status.json()["document_id"]
    assert (
        len(client.get(f"/internal/v1/documents/{document_id}/versions", headers=AUTH).json()) == 1
    )
    index = client.get("/internal/v1/evidence/indexes/status", headers=AUTH)
    assert index.status_code == 200 and index.json()["vector_mode"] == "disabled"
    for endpoint in ("rebuild", "rollback", "reconcile"):
        response = client.post(f"/internal/v1/evidence/indexes/{endpoint}", headers=headers)
        assert response.status_code == 202
    diagnostics = client.post(
        "/internal/v1/evidence/search/diagnostics",
        headers=AUTH,
        json={"query": "secret query", "filters": {"language": "zh"}},
    )
    assert diagnostics.json()["degraded_reason"] == "vector_disabled"
    deleted = client.delete(f"/internal/v1/documents/{document_id}", headers=headers)
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
