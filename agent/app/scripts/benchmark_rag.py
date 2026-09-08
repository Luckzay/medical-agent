from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from app.core.config import Settings
from app.models.evidence import LiteratureSearchInput
from app.services.evidence_store import EvidenceStore
from app.services.hybrid_retrieval import HybridRetriever
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.rag_evaluation import (
    BenchmarkBackend,
    GoldenQuery,
    ModeReport,
    RetrievalRun,
    load_dataset,
    run_benchmark,
)
from app.services.rerankers import cached_reranker
from app.services.runtime import build_runtime


class RealRetrievalBackend(BenchmarkBackend):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.evidence = EvidenceStore(
            settings.evidence_source_path, settings.evidence_database_path
        )
        self.repository = SQLiteCanonicalRepository(settings.canonical_database_path)
        self.runtime = build_runtime(settings)
        self.store = self.runtime.store
        if self.store is None:
            raise RuntimeError("Qdrant runtime is disabled")

    def _lexical(self, query: GoldenQuery, limit: int) -> tuple[list[str], list[str], int]:
        output = self.evidence.search(
            LiteratureSearchInput(query=query.query_en, top_k=min(limit, 100))
        )
        evidence_ids: list[str] = []
        chunk_ids: list[str] = []
        broken = 0
        for hit in output.hits:
            evidence_id = f"literature:{hit.document_id}"
            try:
                _, _, chunk_id = self.repository.resolve_legacy(query.scope, evidence_id)
            except KeyError:
                broken += 1
                continue
            evidence_ids.append(evidence_id)
            chunk_ids.append(chunk_id)
        return evidence_ids, chunk_ids, broken

    def retrieve(
        self, mode: str, query: GoldenQuery, parameters: Mapping[str, Any]
    ) -> RetrievalRun:
        assert self.store is not None
        started = monotonic()
        top_k = int(parameters.get("top_k", 10))
        lexical_limit = int(parameters.get("lexical_candidate_limit", 100))
        vector_limit = int(parameters.get("vector_candidate_limit", 100))
        lexical_ids, lexical_chunks, lexical_broken = self._lexical(query, lexical_limit)
        if mode == "lexical":
            return RetrievalRun(
                evidence_ids=tuple(lexical_ids[:top_k]),
                latency_ms=(monotonic() - started) * 1000,
                broken_lineage=lexical_broken,
            )
        if mode == "vector":
            vector = self.runtime.embedding.embed_query(query.query_en)
            candidates = self.store.search(
                self.settings.qdrant_collection_alias,
                vector,
                query.scope,
                vector_limit,
            )
            mappings = self.repository.resolve_chunks_to_legacy(
                query.scope, [item.chunk_id for item in candidates]
            )
            ids = [mappings[item.chunk_id][0] for item in candidates if item.chunk_id in mappings]
            return RetrievalRun(
                evidence_ids=tuple(ids[:top_k]),
                latency_ms=(monotonic() - started) * 1000,
                broken_lineage=len(candidates) - len(mappings),
            )
        reranker_mode = "optional" if mode == "hybrid_reranker" else "disabled"
        reranker_provider = (
            self.settings.reranker_provider if reranker_mode != "disabled" else "disabled"
        )
        result = HybridRetriever(
            self.repository,
            self.runtime.embedding,
            self.store,
            self.settings.qdrant_collection_alias,
            rrf_k=int(parameters.get("rrf_k", self.settings.fusion_rrf_k)),
            policy_version=self.settings.fusion_policy_version,
            reranker=cached_reranker(
                reranker_provider,
                self.settings.reranker_model,
                self.settings.reranker_revision,
                self.settings.reranker_device,
                self.settings.reranker_batch_size,
            ),
            reranker_mode=reranker_mode,
            reranker_candidate_limit=self.settings.reranker_candidate_limit,
        ).search(query.query_en, query.scope, lexical_chunks, limit=top_k)
        mappings = self.repository.resolve_chunks_to_legacy(
            query.scope, [item.chunk_id for item in result.chunks]
        )
        ids = [mappings[item.chunk_id][0] for item in result.chunks if item.chunk_id in mappings]
        return RetrievalRun(
            evidence_ids=tuple(ids),
            latency_ms=(monotonic() - started) * 1000,
            broken_lineage=result.broken_lineage + len(result.chunks) - len(mappings),
            diagnostics={"degraded": result.degraded},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible real RAG benchmark")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260809)
    args = parser.parse_args()
    settings = Settings()
    dataset = load_dataset(args.dataset)
    parameters: dict[str, Any] = {
        "top_k": 10,
        "lexical_candidate_limit": settings.lexical_candidate_limit,
        "vector_candidate_limit": settings.vector_candidate_limit,
        "rrf_k": settings.fusion_rrf_k,
        "chunk_budget": settings.chunk_token_budget,
        "chunk_overlap": settings.chunk_token_overlap,
        "chunk_parameter_interpretation": (
            "not-applicable: structured rows are equivalent single chunks"
        ),
    }
    backend = RealRetrievalBackend(settings)
    generation = (
        backend.runtime.manifest.generation
        if backend.runtime.manifest is not None
        else "missing-manifest"
    )
    report = run_benchmark(
        dataset,
        backend,
        model_fingerprint=settings.embedding_fingerprint,
        collection_alias=settings.qdrant_collection_alias,
        collection_generation=generation,
        parameters=parameters,
        random_seed=args.seed,
        modes=(
            ("lexical", "vector", "hybrid_rrf", "hybrid_reranker")
            if settings.reranker_provider != "disabled"
            else ("lexical", "vector", "hybrid_rrf")
        ),
        candidate_models={
            "BAAI/bge-m3": "not_run",
            settings.reranker_model: (
                "configured" if settings.reranker_provider == "cross_encoder" else "not_run"
            ),
        },
    )
    if settings.reranker_provider == "disabled":
        report.modes["hybrid_reranker"] = ModeReport(
            status="not_run",
            reason="real reranker provider is disabled; no score was fabricated",
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(report.to_markdown(), encoding="utf-8")


if __name__ == "__main__":
    main()
