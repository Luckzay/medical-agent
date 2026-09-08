from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from app.core.config import Settings, get_settings
from app.models.evidence import LiteratureSearchHit, LiteratureSearchInput
from app.models.knowledge import OwnershipScope
from app.models.tooling import SearchLiteratureOutput
from app.services.evidence_store import EvidenceStore
from app.services.hybrid_retrieval import HybridRetriever
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.rerankers import RequiredRerankerError, cached_reranker
from app.services.retrieval_query import build_retrieval_query
from app.services.runtime import build_runtime


class RequiredVectorUnavailable(RuntimeError):
    pass


class RequiredRerankerUnavailable(RuntimeError):
    pass


@dataclass
class EvidenceRetrievalService:
    settings: Settings
    evidence_store: EvidenceStore
    repository: SQLiteCanonicalRepository

    def _scope(
        self, request: LiteratureSearchInput, trusted_scope: OwnershipScope | None
    ) -> OwnershipScope:
        if trusted_scope is not None:
            return trusted_scope
        return OwnershipScope(
            tenant_id=request.tenant_id or self.settings.evidence_tenant_id,
            project_id=request.project_id or self.settings.evidence_project_id,
        )

    def _lexical_chunk_map(
        self, scope: OwnershipScope, hits: list[LiteratureSearchHit]
    ) -> tuple[list[str], dict[str, LiteratureSearchHit]]:
        chunk_ids: list[str] = []
        by_chunk: dict[str, LiteratureSearchHit] = {}
        for hit in hits:
            try:
                document_id, version_id, chunk_id = self.repository.resolve_legacy(
                    scope, f"literature:{hit.document_id}"
                )
            except KeyError:
                continue
            by_chunk[chunk_id] = hit.model_copy(
                update={
                    "canonical_document_id": document_id,
                    "version_id": version_id,
                    "chunk_id": chunk_id,
                }
            )
            chunk_ids.append(chunk_id)
        return chunk_ids, by_chunk

    def search(
        self, request: LiteratureSearchInput, *, trusted_scope: OwnershipScope | None = None
    ) -> SearchLiteratureOutput:
        mode = request.retrieval_mode or self.settings.vector_mode
        scope = self._scope(request, trusted_scope)
        built = build_retrieval_query(
            query=request.query,
            research_goal=request.research_goal,
            herbs=request.herbs,
            compounds=request.compounds,
            smiles=request.smiles,
        )
        lexical_request = request.model_copy(
            update={
                "query": built.lexical,
                "top_k": min(100, self.settings.lexical_candidate_limit),
            }
        )
        lexical = self.evidence_store.search(lexical_request)
        if mode == "disabled":
            return SearchLiteratureOutput(
                hits=lexical.hits[: request.top_k],
                total_candidates=lexical.total_candidates,
                source_sha256=lexical.source_sha256,
                retrieval_mode="lexical",
            )
        try:
            runtime = build_runtime(self.settings)
            if runtime.store is None:
                raise RuntimeError("vector store is disabled")
            chunk_ids, by_chunk = self._lexical_chunk_map(scope, lexical.hits)
            exact = {chunk_id: tuple(hit.matched_fields) for chunk_id, hit in by_chunk.items()}
            result = HybridRetriever(
                self.repository,
                runtime.embedding,
                runtime.store,
                self.settings.qdrant_collection_alias,
                rrf_k=self.settings.fusion_rrf_k,
                policy_version=self.settings.fusion_policy_version,
                reranker=cached_reranker(
                    self.settings.reranker_provider,
                    self.settings.reranker_model,
                    self.settings.reranker_revision,
                    self.settings.reranker_device,
                    self.settings.reranker_batch_size,
                ),
                reranker_mode=self.settings.reranker_mode,
                reranker_candidate_limit=self.settings.reranker_candidate_limit,
            ).search(built.vector, scope, chunk_ids, limit=request.top_k, exact_boosts=exact)
            reason = (
                result.diagnostics[0].degraded_reason
                if result.diagnostics
                else ("vector unavailable" if result.degraded else None)
            )
            if result.degraded and reason != "reranker_unavailable":
                raise RuntimeError(reason)
            mappings = self.repository.resolve_chunks_to_legacy(
                scope, [chunk.chunk_id for chunk in result.chunks]
            )
            missing_ids = [
                mapping[0].removeprefix("literature:")
                for chunk_id, mapping in mappings.items()
                if chunk_id not in by_chunk
            ]
            by_evidence = {
                hit.document_id: hit for hit in self.evidence_store.get_hits(missing_ids)
            }
            hits: list[LiteratureSearchHit] = []
            for chunk, diagnostic in zip(result.chunks, result.diagnostics, strict=True):
                mapping = mappings.get(chunk.chunk_id)
                if mapping is None:
                    continue
                evidence_id, document_id, version_id = mapping
                hit = by_chunk.get(chunk.chunk_id) or by_evidence.get(
                    evidence_id.removeprefix("literature:")
                )
                if hit is None:
                    continue
                scores = {
                    **hit.channel_scores,
                    "lexical_rank": float(diagnostic.lexical_rank or 0),
                    "vector_rank": float(diagnostic.vector_rank or 0),
                    "fused_rank": float(diagnostic.fused_rank or 0),
                    "rerank_rank": float(diagnostic.rerank_rank or 0),
                    "rerank_score": float(diagnostic.rerank_score or 0),
                }
                hits.append(
                    hit.model_copy(
                        update={
                            "canonical_document_id": document_id,
                            "version_id": version_id,
                            "chunk_id": chunk.chunk_id,
                            "source_locator": chunk.locator.model_dump(mode="json"),
                            "retrieval_diagnostics": diagnostic.model_dump(mode="json"),
                            "channel_scores": scores,
                        }
                    )
                )
            diagnostics = (
                [item.model_dump(mode="json") for item in result.diagnostics]
                if request.diagnostics
                else []
            )
            return SearchLiteratureOutput(
                hits=hits,
                total_candidates=len(hits),
                source_sha256=lexical.source_sha256,
                degraded=result.degraded,
                retrieval_mode=(
                    "hybrid_reranker"
                    if any(item.rerank_rank is not None for item in result.diagnostics)
                    else "hybrid"
                ),
                diagnostics=diagnostics,
                degraded_reason=reason if result.degraded else None,
            )
        except Exception as exc:
            if isinstance(exc, RequiredRerankerError):
                raise RequiredRerankerUnavailable(
                    "required reranker is unavailable"
                ) from exc
            if mode == "required":
                raise RequiredVectorUnavailable("required vector retrieval is unavailable") from exc
            return SearchLiteratureOutput(
                hits=lexical.hits[: request.top_k],
                total_candidates=lexical.total_candidates,
                source_sha256=lexical.source_sha256,
                degraded=True,
                retrieval_mode="lexical",
                degraded_reason=type(exc).__name__,
            )


_shared: EvidenceRetrievalService | None = None
_lock = Lock()


def get_retrieval_service(settings: Settings | None = None) -> EvidenceRetrievalService:
    global _shared
    with _lock:
        if _shared is None:
            current = settings or get_settings()
            _shared = EvidenceRetrievalService(
                current,
                EvidenceStore(current.evidence_source_path, current.evidence_database_path),
                SQLiteCanonicalRepository(current.canonical_database_path),
            )
        return _shared
