from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from app.models.evidence import LiteratureSearchInput, LiteratureSearchOutput
from app.models.knowledge import DocumentChunk, OwnershipScope, RetrievalDiagnostics
from app.services.embeddings import EmbeddingProvider
from app.services.evidence_store import EvidenceStore
from app.services.knowledge_observability import metrics
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.rerankers import RequiredRerankerError, RerankerProvider, validate_scores
from app.services.vector_index import QdrantVectorStore


@dataclass(frozen=True)
class RankedCandidate:
    identifier: str
    score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None
    exact_fields: tuple[str, ...] = ()


class LexicalRetrievalChannel:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def search(self, request: LiteratureSearchInput) -> LiteratureSearchOutput:
        return self.store.search(request)


def reciprocal_rank_fusion(
    lexical: list[str],
    vector: list[str],
    *,
    rrf_k: int = 60,
    exact_boosts: dict[str, tuple[str, ...]] | None = None,
) -> list[RankedCandidate]:
    lexical_ranks = {identifier: rank for rank, identifier in enumerate(lexical, 1)}
    vector_ranks = {identifier: rank for rank, identifier in enumerate(vector, 1)}
    exact_boosts = exact_boosts or {}
    output: list[RankedCandidate] = []
    for identifier in lexical_ranks.keys() | vector_ranks.keys():
        lexical_rank, vector_rank = lexical_ranks.get(identifier), vector_ranks.get(identifier)
        score = (1 / (rrf_k + lexical_rank) if lexical_rank else 0) + (
            1 / (rrf_k + vector_rank) if vector_rank else 0
        )
        exact = exact_boosts.get(identifier, ())
        score += 1.0 * bool({"doi", "smiles"}.intersection(exact))
        output.append(RankedCandidate(identifier, score, lexical_rank, vector_rank, exact))
    return sorted(output, key=lambda item: (-item.score, item.identifier))


@dataclass
class HybridResult:
    chunks: list[DocumentChunk]
    diagnostics: list[RetrievalDiagnostics]
    degraded: bool
    broken_lineage: int = 0


class HybridRetriever:
    def __init__(
        self,
        repository: SQLiteCanonicalRepository,
        embedding: EmbeddingProvider,
        vector_store: QdrantVectorStore | None,
        alias: str,
        *,
        rrf_k: int = 60,
        policy_version: str = "rrf-v1",
        reranker: RerankerProvider | None = None,
        reranker_mode: str = "disabled",
        reranker_candidate_limit: int = 50,
    ) -> None:
        self.repository, self.embedding, self.vector_store = repository, embedding, vector_store
        self.alias, self.rrf_k, self.policy_version = alias, rrf_k, policy_version
        self.reranker = reranker
        self.reranker_mode = reranker_mode
        self.reranker_candidate_limit = reranker_candidate_limit

    def search(
        self,
        query: str,
        scope: OwnershipScope,
        lexical_chunk_ids: list[str],
        *,
        limit: int = 10,
        filters: dict[str, object] | None = None,
        exact_boosts: dict[str, tuple[str, ...]] | None = None,
    ) -> HybridResult:
        started = monotonic()
        vector_ids: list[str] = []
        degraded_reason: str | None = None
        if self.vector_store is None:
            degraded_reason = "vector_disabled"
        else:
            try:
                vector = self.embedding.embed_query(query)
                vector_ids = [
                    candidate.chunk_id
                    for candidate in self.vector_store.search(
                        self.alias, vector, scope, limit * 5, filters
                    )
                ]
            except Exception:
                degraded_reason = "vector_unavailable"
        fused = reciprocal_rank_fusion(
            lexical_chunk_ids, vector_ids, rrf_k=self.rrf_k, exact_boosts=exact_boosts
        )
        resolved = self.repository.get_chunks(
            scope, [item.identifier for item in fused], active_only=True
        )
        by_id = {chunk.chunk_id: chunk for chunk in resolved}
        # Authorization and canonical lineage are resolved before any passage reaches a reranker.
        eligible = [item for item in fused if item.identifier in by_id]
        fused_ranks = {item.identifier: rank for rank, item in enumerate(eligible, 1)}
        rerank_scores: dict[str, float] = {}
        rerank_reason: str | None = None
        if self.reranker_mode != "disabled":
            candidates = eligible[: self.reranker_candidate_limit]
            try:
                if self.reranker is None:
                    raise RuntimeError("reranker is not configured")
                raw_scores = self.reranker.score(
                    query, [by_id[item.identifier].text for item in candidates]
                )
                scores = validate_scores(raw_scores, len(candidates))
                rerank_scores = {
                    item.identifier: score for item, score in zip(candidates, scores, strict=True)
                }
                reranked = sorted(
                    candidates,
                    key=lambda item: (-rerank_scores[item.identifier], item.identifier),
                )
                eligible = reranked + eligible[len(candidates) :]
            except Exception as exc:
                if self.reranker_mode == "required":
                    raise RequiredRerankerError("required reranking failed") from exc
                rerank_reason = "reranker_unavailable"
        eligible = eligible[:limit]
        latency = (monotonic() - started) * 1000
        metrics.increment("retrieval_lexical_queries")
        if vector_ids:
            metrics.increment("retrieval_vector_queries")
        if degraded_reason or rerank_reason:
            metrics.increment("retrieval_degraded")
        metrics.gauge("reconciliation_broken_lineage", float(len(fused) - len(resolved)))
        diagnostics = [
            RetrievalDiagnostics(
                mode=("hybrid_reranker" if rerank_scores else "hybrid")
                if vector_ids
                else "lexical",
                policy_version=self.policy_version,
                lexical_rank=item.lexical_rank,
                vector_rank=item.vector_rank,
                fused_rank=fused_ranks[item.identifier],
                rerank_rank=rank if item.identifier in rerank_scores else None,
                rerank_score=rerank_scores.get(item.identifier),
                reranker_fingerprint=(
                    self.reranker.fingerprint
                    if self.reranker is not None and item.identifier in rerank_scores
                    else None
                ),
                exact_matches=item.exact_fields,
                embedding_fingerprint=self.embedding.fingerprint if vector_ids else None,
                latency_ms=latency,
                degraded_reason=degraded_reason or rerank_reason,
            )
            for rank, item in enumerate(eligible, 1)
        ]
        return HybridResult(
            [by_id[item.identifier] for item in eligible],
            diagnostics,
            degraded_reason is not None or rerank_reason is not None,
            len(fused) - len(resolved),
        )
