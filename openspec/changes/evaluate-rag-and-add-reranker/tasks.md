## 1. Dataset and experiment contracts
- [x] 1.1 Add strict versioned graded dataset schema, canonical hash, validation, and human annotation entry point
- [x] 1.2 Add an honest weak-labelled bilingual seed grounded in the 131 real literature rows
- [x] 1.3 Add embedding cache/generation isolation and explicit structured-row chunk equivalence metadata

## 2. Benchmarking
- [x] 2.1 Implement graded IR metrics, irrelevant and broken-lineage rates, average/P95 latency
- [x] 2.2 Implement deterministic four-mode runner and JSON/Markdown reports with complete reproducibility metadata
- [x] 2.3 Add parameter-grid support and candidate-model `not_run` records
- [x] 2.4 Attempt the real pinned E5/131-point baseline and record truthful status/results

## 3. Reranking
- [x] 3.1 Implement provider protocol plus disabled, deterministic, and lazy cross-encoder providers with score validation
- [x] 3.2 Integrate post-scope/post-lineage reranking, stable ordering, optional fallback, and required failure
- [x] 3.3 Extend retrieval diagnostics and preserve default disabled output

## 4. Interfaces and documentation
- [x] 4.1 Update configuration, API, Tool/MCP schema, OpenAPI, README, and environment examples
- [x] 4.2 Document model selection, resource-aware execution, cache/generation rules, weak-label limitations, and human annotation workflow

## 5. Verification
- [x] 5.1 Test metric correctness, graded relevance, dataset validation/hash, and runner reproducibility without Qdrant/model downloads
- [x] 5.2 Test retrieval modes, reranker ordering/ties/failure semantics, scope/lineage safety, workflow/Tool/MCP regressions
- [x] 5.3 Run complete pytest, Ruff, strict mypy, uv lock, Go tests, OpenAPI/YAML parse, both OpenSpec strict validations, and git diff check
