# Change: Evaluate RAG quality and add optional reranking

## Why
Retrieval has a real 131-document E5/Qdrant baseline but no versioned graded dataset, reproducible cross-mode benchmark, or safe reranking extension. Quality claims therefore cannot be audited or compared.

## What Changes
- Add a versioned golden-retrieval schema, validation/hash tooling, an explicitly weak-labelled seed derived from the real literature corpus, and a human annotation entry point.
- Add deterministic offline benchmarks for lexical, vector, hybrid RRF, and hybrid plus reranker with graded IR, lineage, and latency metrics.
- Add configurable embedding experiment metadata/cache isolation and parameter grids without inventing unavailable model results.
- Add disabled, deterministic-test, and lazy cross-encoder reranker providers and integrate reranking after authorization/lineage filtering.
- Extend API/tool/MCP diagnostics, configuration, OpenAPI, environment examples, and operations documentation.

## Impact
Default reranking remains disabled, preserving current behavior. Enabled optional reranking degrades to fused order on provider failure; required reranking fails explicitly. Different embedding dimensions require separate collection generations.