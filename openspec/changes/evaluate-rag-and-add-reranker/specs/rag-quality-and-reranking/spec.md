## ADDED Requirements

### Requirement: Versioned graded retrieval dataset
The system SHALL validate and canonically hash a versioned retrieval dataset containing query identity, Chinese and English query forms, research goal, authorization scope, graded relevant evidence, hard negatives, tags, and annotation provenance.

#### Scenario: Weak seed labels are loaded
- **WHEN** labels were automatically derived from the 131-row literature corpus
- **THEN** provenance is explicitly `weak` or `synthetic` and reports warn that results are not a final human quality conclusion

#### Scenario: Human annotation is extended
- **WHEN** an annotator adds or changes a judgment
- **THEN** the strict validator accepts grades 0 through 3, records annotator/method/time, rejects contradictory IDs, and produces a new dataset hash

### Requirement: Reproducible retrieval benchmark
The system SHALL compare lexical-only, vector-only, hybrid RRF, and hybrid plus reranker using Recall@1/3/5/10, Precision@K, MRR@10, nDCG@10, irrelevant-evidence rate, broken-lineage rate, and average/P95 latency.

#### Scenario: Benchmark is repeated
- **WHEN** dataset, backend, parameters, model fingerprint, collection generation, and random seed are unchanged
- **THEN** rankings, metrics, and report metadata are identical apart from explicitly separated wall-clock observations

#### Scenario: Candidate model was not run
- **WHEN** BGE-M3 or another candidate was declared but not locally executed
- **THEN** the report records `not_run` and contains no fabricated metrics

### Requirement: Isolated embedding experiments
The system SHALL key reusable embedding caches and collection generations by complete model fingerprint and vector dimension.

#### Scenario: Embedding dimension changes
- **WHEN** an experiment selects a model with a different dimension
- **THEN** it uses an independent collection generation and cannot reuse incompatible vectors

#### Scenario: Structured-row chunk parameters vary
- **WHEN** chunk budget or overlap is varied for current one-row/one-chunk records
- **THEN** the experiment declares the parameter inapplicable or single-chunk equivalent rather than claiming a fabricated quality difference

### Requirement: Safe optional reranking
The system SHALL provide disabled, deterministic-test, and lazy cross-encoder rerankers that score query-passage pairs, validate finite one-to-one scores, preserve stable tie-breaking, and operate only on authorized lineage-resolved candidates.

#### Scenario: Reranking is disabled
- **WHEN** the default configuration is used
- **THEN** fused ordering and existing retrieval output remain unchanged

#### Scenario: Optional reranker fails
- **WHEN** optional reranking raises or returns invalid scores
- **THEN** the system returns fused ordering with a sanitized degraded diagnostic

#### Scenario: Required reranker fails
- **WHEN** required reranking raises or returns invalid scores
- **THEN** retrieval fails explicitly and does not silently return fused output

#### Scenario: Service starts
- **WHEN** a real cross-encoder is configured
- **THEN** model libraries and weights are not imported or downloaded until the first enabled rerank request

### Requirement: Reranker interface compatibility
The system SHALL expose reranker controls and sanitized diagnostics through the Evidence Retrieval Service, `search_literature`, Tool/MCP schemas, OpenAPI, README, and environment examples without weakening trusted scope.

#### Scenario: Model-controlled scope and reranker options are supplied
- **WHEN** trusted execution context provides scope and server policy
- **THEN** trusted scope and server safety policy take precedence and no unauthorized candidate appears before or after reranking
