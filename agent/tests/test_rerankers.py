from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.models.knowledge import OwnershipScope
from app.services.embeddings import DeterministicTestEmbedding
from app.services.hybrid_retrieval import HybridRetriever
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.rerankers import (
    DeterministicTestReranker,
    LazyCrossEncoderReranker,
    RequiredRerankerError,
    RerankerError,
    validate_scores,
)
from tests.test_hybrid_retrieval import add_chunk


class FakeCrossEncoder:
    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int) -> list[float]:
        del batch_size
        return [float(len(passage)) for _, passage in pairs]


class FixedReranker:
    fingerprint = "fixed:v1"

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.passages: list[str] = []

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        del query
        self.passages = list(passages)
        return self.scores


def test_deterministic_reranker_and_score_validation() -> None:
    provider = DeterministicTestReranker()
    assert provider.score("alpha beta", ["beta", "none"]) == [1.0, 0.0]
    with pytest.raises(RerankerError):
        validate_scores([1.0], 2)
    with pytest.raises(RerankerError):
        validate_scores([math.nan], 1)


def test_cross_encoder_is_lazy_and_validates_output() -> None:
    loads = 0

    def loader() -> Any:
        nonlocal loads
        loads += 1
        return FakeCrossEncoder()

    provider = LazyCrossEncoderReranker("model", "revision", loader=loader)
    assert not provider.loaded and loads == 0
    assert provider.score("q", ["a", "long"]) == [1.0, 4.0]
    assert provider.loaded and loads == 1


def test_rerank_happens_after_scope_and_lineage_with_stable_ties(tmp_path: Path) -> None:
    repository = SQLiteCanonicalRepository(tmp_path / "rerank.db")
    scope = OwnershipScope(tenant_id="t", project_id="p")
    first = add_chunk(repository, scope, "a", "first passage")
    second = add_chunk(repository, scope, "b", "second passage")
    provider = FixedReranker([1.0, 1.0])
    result = HybridRetriever(
        repository,
        DeterministicTestEmbedding(8),
        None,
        "unused",
        reranker=provider,
        reranker_mode="optional",
    ).search("query", scope, [second.chunk_id, "broken", first.chunk_id], limit=10)
    assert "broken" not in provider.passages
    assert [item.chunk_id for item in result.chunks] == sorted([first.chunk_id, second.chunk_id])
    assert all(item.reranker_fingerprint == "fixed:v1" for item in result.diagnostics)
    assert result.broken_lineage == 1


def test_optional_failure_falls_back_and_required_failure_is_explicit(tmp_path: Path) -> None:
    repository = SQLiteCanonicalRepository(tmp_path / "failure.db")
    scope = OwnershipScope(tenant_id="t", project_id="p")
    chunk = add_chunk(repository, scope, "safe", "authorized passage")
    invalid = FixedReranker([math.nan])
    optional = HybridRetriever(
        repository,
        DeterministicTestEmbedding(8),
        None,
        "unused",
        reranker=invalid,
        reranker_mode="optional",
    ).search("query", scope, [chunk.chunk_id])
    assert optional.chunks == [chunk]
    assert optional.diagnostics[0].degraded_reason == "vector_disabled"
    required = HybridRetriever(
        repository,
        DeterministicTestEmbedding(8),
        None,
        "unused",
        reranker=invalid,
        reranker_mode="required",
    )
    with pytest.raises(RequiredRerankerError):
        required.search("query", scope, [chunk.chunk_id])
