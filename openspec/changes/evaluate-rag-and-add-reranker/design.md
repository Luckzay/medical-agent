## Context
The canonical corpus has 131 structured literature rows, each equivalent to one chunk for current experiments. The production baseline is `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions. Existing retrieval filters scope and resolves canonical lineage before returning evidence.

## Decisions
1. Dataset JSON uses strict Pydantic models and canonical SHA-256. Every query carries bilingual text, goal, scope, graded evidence IDs, hard negatives, tags, and annotation provenance. `weak`/`synthetic` provenance is never presented as human gold.
2. Metrics are pure deterministic functions. Ranking ties are broken by stable evidence ID. Reports pin dataset hash, model fingerprint, alias/generation, complete parameters, seed, runtime status, and raw per-query latency.
3. Benchmark retrieval is behind a protocol so unit tests need neither Qdrant nor model downloads. Real providers are only invoked explicitly.
4. Embedding cache keys include provider fingerprint and text hash. Collection-generation identity includes dimension, preventing incompatible reuse. Structured rows declare chunk budget/overlap equivalent single-chunk and do not claim a quality difference.
5. Reranking receives only already authorized, lineage-resolved candidates. Scores must be finite and one-to-one. The deterministic provider supports tests; cross-encoder imports and loads only on first rerank call.
6. Reranker modes are `disabled`, `optional`, and `required`. Optional failures retain deterministic fused order and expose a sanitized reason. Required failures raise an explicit service error.
7. Rerank diagnostics include fused rank, rerank rank/score/provider fingerprint, and degradation. Returned candidates are revalidated against the same resolved candidate set.

## Model selection
The preferred multilingual candidate is `BAAI/bge-reranker-v2-m3`; a smaller cross-encoder can be configured for constrained hosts. A declared candidate has status `not_run` until locally available and actually benchmarked. No import/startup path downloads a model.

## Risks and mitigations
- Weak labels inflate apparent retrieval quality: reports carry a prominent non-final warning and provenance summary.
- Reranker latency: candidate limit is bounded and P95 is reported.
- Provider failure: explicit optional/required semantics.
- Dimension mismatch: generation fingerprint includes dimension and validation rejects cache mismatch.

## Rollout
Keep defaults disabled. Validate deterministic provider and offline fixture benchmark first, then run the pinned E5 real baseline against the active 131-point collection when infrastructure and cache are available. Human reviewers replace weak labels before quality-gate decisions.