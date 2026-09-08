from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from qdrant_client import models

from app.api.routes import get_supramolecular_search_service
from app.main import app
from app.models.supramolecular import SupramolecularSearchRequest
from app.services.embeddings import DeterministicTestEmbedding
from app.services.supramolecular_retrieval import (
    SupramolecularSearchService,
    build_qdrant_filter,
)


class FakeQdrant:
    def __init__(self) -> None:
        self.query_filter: models.Filter | None = None

    def query_points(self, **kwargs: Any) -> SimpleNamespace:
        self.query_filter = kwargs["query_filter"]
        # 向量顺序：2、1、3；词法顺序：1、3、2，因此混排后 1 应排到 2 前。
        points = [
            SimpleNamespace(id="2", score=0.95, payload={"id": 2, "search_text": "无关"}),
            SimpleNamespace(
                id="1",
                score=0.90,
                payload={
                    "id": 1,
                    "outcome_status": "SUCCESS",
                    "compound_name": ["黄芩苷"],
                    "search_text": "黄芩苷 黄芩苷 自组装 纳米纤维",
                },
            ),
            SimpleNamespace(id="3", score=0.80, payload={"id": 3, "search_text": "自组装"}),
        ]
        return SimpleNamespace(points=points[: kwargs["limit"]])


class BrokenSummary:
    def summarize(self, query: str, experiments: Sequence[dict[str, Any]]) -> str:
        raise RuntimeError("provider unavailable")


@pytest.fixture
def fake_service() -> SupramolecularSearchService:
    return SupramolecularSearchService(
        cast(Any, FakeQdrant()),
        DeterministicTestEmbedding(8),
        candidate_multiplier=3,
        summarizer=BrokenSummary(),
    )


def test_search_validation_rejects_blank_query_unknown_filter_and_invalid_top_k(
    fake_service: SupramolecularSearchService,
) -> None:
    app.dependency_overrides[get_supramolecular_search_service] = lambda: fake_service
    client = TestClient(app)
    try:
        for body in (
            {"query": "   "},
            {"query": "test", "top_k": 0},
            {"query": "test", "filters": {"unknown": "value"}},
            {"query": "test", "filters": {"outcome_status": "UNKNOWN"}},
            {"query": "test", "filters": {"ph_min": 15}},
        ):
            response = client.post("/supramolecular/search", json=body)
            assert response.status_code == 422
            assert response.json() == {"detail": "Request validation failed"}
    finally:
        app.dependency_overrides.clear()


def test_filter_translation_supports_status_text_and_ranges() -> None:
    request = SupramolecularSearchRequest.model_validate(
        {
            "query": "黄芩苷",
            "filters": {
                "outcome_status": "SUCCESS",
                "compound_name": "黄芩苷",
                "solvent_type": "水",
                "assembly_morphology": "纤维",
                "interaction_type": "氢键",
                "metal_ion": "Zn2+",
                "ph_min": 5,
                "ph_max": 8,
                "temperature_min_c": 20,
                "temperature_max_c": 40,
            },
        }
    )
    query_filter = build_qdrant_filter(request.filters)
    assert query_filter is not None
    assert isinstance(query_filter.must, list)
    fields = {
        condition.key
        for condition in query_filter.must
        if isinstance(condition, models.FieldCondition)
    }
    assert fields == {
        "outcome_status",
        "compound_name",
        "solvent_types",
        "morphologies_filter",
        "interaction_types",
        "metal_ions",
        "ph_min",
        "ph_max",
        "temperature_min_c",
        "temperature_max_c",
    }


def test_hybrid_sort_and_summary_failure_falls_back(
    fake_service: SupramolecularSearchService,
) -> None:
    result = fake_service.search(SupramolecularSearchRequest(query="黄芩苷 自组装", top_k=3))
    assert [item.id for item in result.experiments][:2] == [1, 2]
    assert result.experiments[0].relevance_score >= result.experiments[1].relevance_score
    assert result.summary is None
    assert "search_text" not in result.experiments[0].model_dump()


def test_endpoint_uses_dependency_and_returns_results(
    fake_service: SupramolecularSearchService,
) -> None:
    app.dependency_overrides[get_supramolecular_search_service] = lambda: fake_service
    try:
        response = TestClient(app).post(
            "/supramolecular/search",
            json={"query": "黄芩苷 自组装", "top_k": 2, "filters": {"outcome_status": "SUCCESS"}},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["summary"] is None
    assert all("relevance_score" in item for item in body["experiments"])
