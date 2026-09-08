from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.knowledge import OwnershipScope
from app.services.rag_evaluation import (
    AnnotationProvenance,
    BenchmarkBackend,
    EmbeddingCache,
    GoldenDataset,
    GoldenQuery,
    RelevanceJudgment,
    RetrievalRun,
    collection_generation_key,
    load_dataset,
    mrr_at,
    ndcg_at,
    parameter_grid,
    precision_at,
    recall_at,
    run_benchmark,
)


class FixtureBackend(BenchmarkBackend):
    def retrieve(
        self, mode: str, query: GoldenQuery, parameters: Mapping[str, Any]
    ) -> RetrievalRun:
        del parameters
        relevant = query.relevant_evidence[0].evidence_id
        ranking = (relevant, "irrelevant") if mode != "vector" else ("irrelevant", relevant)
        return RetrievalRun(evidence_ids=ranking, latency_ms=2.0, broken_lineage=0)


def test_seed_dataset_is_valid_hashed_and_explicitly_weak() -> None:
    path = Path("resources/evaluation/golden_retrieval_seed_v1.json")
    dataset = load_dataset(path)
    assert dataset.is_weak
    assert len(dataset.queries) == 6
    assert len(dataset.sha256) == 64
    assert dataset.sha256 == load_dataset(path).sha256
    assert all(query.provenance.label_type == "weak" for query in dataset.queries)


def test_dataset_rejects_contradictory_and_duplicate_annotations() -> None:
    provenance = AnnotationProvenance(
        label_type="human", method="dual review", annotator="expert", annotated_at="2026-08-09"
    )
    with pytest.raises(ValidationError):
        GoldenQuery(
            query_id="q",
            query_zh="查询",
            query_en="query",
            research_goal="goal",
            scope=OwnershipScope(tenant_id="t", project_id="p"),
            relevant_evidence=(RelevanceJudgment(evidence_id="e", grade=3),),
            hard_negatives=("e",),
            tags=("human",),
            provenance=provenance,
        )


def test_graded_ir_metrics() -> None:
    grades = {"high": 3, "low": 1, "zero": 0}
    assert recall_at(["low", "other", "high"], grades, 1) == 0.5
    assert recall_at(["low", "other", "high"], grades, 3) == 1.0
    assert precision_at(["low", "other"], grades, 2) == 0.5
    assert mrr_at(["other", "high"], grades) == 0.5
    assert ndcg_at(["high", "low"], grades) == pytest.approx(1.0)
    assert ndcg_at(["low", "high"], grades) < 1.0


def test_runner_is_reproducible_and_warns_about_weak_labels() -> None:
    dataset = load_dataset("resources/evaluation/golden_retrieval_seed_v1.json")
    first = run_benchmark(
        dataset,
        FixtureBackend(),
        model_fingerprint="e5@revision:d384",
        collection_alias="active",
        collection_generation="g1",
        parameters={"top_k": 10, "rrf_k": 60},
        random_seed=7,
        candidate_models={"BAAI/bge-m3": "not_run"},
    )
    second = run_benchmark(
        dataset,
        FixtureBackend(),
        model_fingerprint="e5@revision:d384",
        collection_alias="active",
        collection_generation="g1",
        parameters={"top_k": 10, "rrf_k": 60},
        random_seed=7,
        candidate_models={"BAAI/bge-m3": "not_run"},
    )
    assert first == second
    assert first.weak_label_warning
    assert first.modes["lexical"].metrics["recall@10"] == 1.0
    assert first.modes["vector"].metrics["mrr@10"] == 0.5
    assert "not_run" in first.to_markdown()


def test_cache_generation_and_parameter_grid_are_isolated(tmp_path: Path) -> None:
    first = collection_generation_key("model-a", 384, "corpus")
    second = collection_generation_key("model-a", 1024, "corpus")
    assert first != second and first.endswith("d384") and second.endswith("d1024")
    path = tmp_path / "cache.json"
    cache = EmbeddingCache(path, "model-a", 2)
    cache.put("text", [1.0, 0.0])
    cache.save()
    assert EmbeddingCache(path, "model-a", 2).get("text") == [1.0, 0.0]
    with pytest.raises(ValueError):
        EmbeddingCache(path, "model-a", 3)
    assert parameter_grid({"top_k": [5, 10], "rrf_k": [30, 60]}) == [
        {"rrf_k": 30, "top_k": 5},
        {"rrf_k": 30, "top_k": 10},
        {"rrf_k": 60, "top_k": 5},
        {"rrf_k": 60, "top_k": 10},
    ]


def test_dataset_json_schema_round_trip_is_strict() -> None:
    payload = json.loads(
        Path("resources/evaluation/golden_retrieval_seed_v1.json").read_text(encoding="utf-8")
    )
    payload["queries"][0]["relevant_evidence"][0]["grade"] = 4
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload, strict=True)
