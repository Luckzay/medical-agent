from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import QdrantClient, models

from app.models.supramolecular import (
    SupramolecularExperimentHit,
    SupramolecularSearchFilters,
    SupramolecularSearchRequest,
    SupramolecularSearchResponse,
)
from app.services.embeddings import EmbeddingProvider
from app.services.hybrid_retrieval import reciprocal_rank_fusion

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_.+-]+|[\u3400-\u9fff]")


class SummaryProvider(Protocol):
    def summarize(self, query: str, experiments: Sequence[dict[str, Any]]) -> str: ...


@dataclass(frozen=True)
class ExperimentCandidate:
    identifier: str
    vector_score: float
    payload: dict[str, Any]


def tokenize(text: str) -> list[str]:
    """轻量中英文化分词：英文词 + 中文单字/双字，避免引入额外运行时依赖。"""
    base = [token.casefold() for token in _TOKEN_RE.findall(text)]
    chinese = [token for token in base if len(token) == 1 and "\u3400" <= token <= "\u9fff"]
    return base + ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]


def bm25_order(query: str, candidates: Sequence[ExperimentCandidate]) -> list[str]:
    """仅在向量召回集合内进行 BM25 排序。"""
    query_terms = tokenize(query)
    if not query_terms or not candidates:
        return [candidate.identifier for candidate in candidates]
    documents = [
        tokenize(str(candidate.payload.get("search_text", ""))) for candidate in candidates
    ]
    average_length = sum(map(len, documents)) / len(documents) or 1.0
    document_frequency = Counter(
        term for document in documents for term in set(document) if term in query_terms
    )
    scores: list[tuple[float, int, str]] = []
    for position, (candidate, document) in enumerate(zip(candidates, documents, strict=True)):
        frequencies = Counter(document)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            score += inverse_frequency * frequency * 2.5 / (
                frequency + 1.5 * (1 - 0.75 + 0.75 * len(document) / average_length)
            )
        scores.append((score, position, candidate.identifier))
    return [identifier for _, _, identifier in sorted(scores, key=lambda item: (-item[0], item[1]))]


def build_qdrant_filter(filters: SupramolecularSearchFilters) -> models.Filter | None:
    must: list[models.Condition] = []
    if filters.outcome_status is not None:
        must.append(models.FieldCondition(
            key="outcome_status", match=models.MatchValue(value=filters.outcome_status.value)
        ))
    text_fields = {
        "compound_name": filters.compound_name,
        "solvent_types": filters.solvent_type,
        "morphologies_filter": filters.assembly_morphology,
        "interaction_types": filters.interaction_type,
        "metal_ions": filters.metal_ion,
    }
    for field, value in text_fields.items():
        if value:
            must.append(models.FieldCondition(key=field, match=models.MatchText(text=value)))
    # 区间相交：实验上界不小于请求下界，实验下界不大于请求上界。
    if filters.ph_min is not None:
        must.append(models.FieldCondition(key="ph_max", range=models.Range(gte=filters.ph_min)))
    if filters.ph_max is not None:
        must.append(models.FieldCondition(key="ph_min", range=models.Range(lte=filters.ph_max)))
    if filters.temperature_min_c is not None:
        must.append(models.FieldCondition(
            key="temperature_max_c", range=models.Range(gte=filters.temperature_min_c)
        ))
    if filters.temperature_max_c is not None:
        must.append(models.FieldCondition(
            key="temperature_min_c", range=models.Range(lte=filters.temperature_max_c)
        ))
    return models.Filter(must=must) if must else None


class SupramolecularSearchService:
    def __init__(
        self,
        client: QdrantClient,
        embedding: EmbeddingProvider,
        collection: str = "supramolecular_experiments_active",
        *,
        candidate_multiplier: int = 5,
        rrf_k: int = 60,
        summarizer: SummaryProvider | None = None,
    ) -> None:
        self.client = client
        self.embedding = embedding
        self.collection = collection
        self.candidate_multiplier = candidate_multiplier
        self.rrf_k = rrf_k
        self.summarizer = summarizer

    def search(self, request: SupramolecularSearchRequest) -> SupramolecularSearchResponse:
        response = self.client.query_points(
            collection_name=self.collection,
            query=self.embedding.embed_query(request.query),
            query_filter=build_qdrant_filter(request.filters),
            limit=min(request.top_k * self.candidate_multiplier, 500),
            with_payload=True,
        )
        candidates = [
            ExperimentCandidate(
                identifier=str(point.id),
                vector_score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in response.points
        ]
        vector_ids = [candidate.identifier for candidate in candidates]
        lexical_ids = bm25_order(request.query, candidates)
        fused = reciprocal_rank_fusion(lexical_ids, vector_ids, rrf_k=self.rrf_k)
        by_id = {candidate.identifier: candidate for candidate in candidates}
        selected = fused[: request.top_k]
        experiments: list[SupramolecularExperimentHit] = []
        for ranked in selected:
            payload = dict(by_id[ranked.identifier].payload)
            payload.pop("search_text", None)
            experiment_id = payload.pop("id", payload.pop("experiment_id", ranked.identifier))
            experiments.append(
                SupramolecularExperimentHit(
                    id=experiment_id,
                    relevance_score=ranked.score,
                    **payload,
                )
            )

        summary: str | None = None
        if self.summarizer is not None and experiments:
            try:
                summary = self.summarizer.summarize(
                    request.query, [item.model_dump() for item in experiments]
                )
            except Exception:
                # 摘要是可选增强能力，失败绝不能影响检索结果。
                summary = None
        return SupramolecularSearchResponse(
            experiments=experiments, summary=summary, total=len(experiments)
        )
