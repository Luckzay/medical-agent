## 1. Foundation and Configuration

- [x] 1.1 Add Qdrant client and optional local embedding dependencies without forcing model downloads during installation or import
- [x] 1.2 Add validated settings for vector mode, Qdrant connection, collection alias, embedding fingerprint, chunk policy, fusion policy, batching, timeout, and worker limits
- [x] 1.3 Define canonical Pydantic models and enums for documents, immutable versions, normalized blocks, chunks, source locators, ingestion jobs, index manifests, and retrieval diagnostics
- [x] 1.4 Define parser, chunker, embedding-provider, canonical repository, and vector-store protocols that do not expose vendor-specific types to workflow models

## 2. Canonical Document Repository

- [x] 2.1 Add SQLite schema initialization and migrations for documents, document versions, blocks, chunks, ingestion jobs, embedding cache, index manifests, and legacy evidence mappings
- [x] 2.2 Implement transactional document/version creation with source-hash deduplication and immutable-version enforcement
- [x] 2.3 Implement chunk, job-state, manifest, activation, tombstone, and historical citation-resolution repository operations
- [x] 2.4 Add ownership-scope fields and enforce tenant/project filters inside repository queries
- [x] 2.5 Add repository tests for unchanged re-import, changed versions, activation, scoped deletion, retry state, and historical lineage

## 3. Parsing and Structure-Aware Chunking

- [x] 3.1 Implement parser and chunker registries with explicit unsupported-media errors and versioned fingerprints
- [x] 3.2 Adapt the existing Excel literature importer to produce normalized structured-row blocks while preserving all 131 legacy Evidence IDs and source rows
- [x] 3.3 Implement initial plain-text and Markdown parsers that preserve heading hierarchy and source positions
- [x] 3.4 Implement the default structure-first chunker with configurable 700-token budget, 100-token overlap, parent context, deterministic UUIDv5 identities, and no blind splitting of structured rows or small tables
- [x] 3.5 Add deterministic parsing and chunking tests for headings, oversized sections, overlap, tables, units, repeat processing, and parser/chunker version changes

## 4. Embedding and Managed Qdrant Index

- [x] 4.1 Implement a lazy-loading embedding-provider adapter with document/query batching, dimension validation, normalization, timeouts, retries, health, and a complete fingerprint
- [x] 4.2 Implement a deterministic non-semantic test embedding provider and embedding-cache tests that require no network or downloaded model weights
- [x] 4.3 Implement the Qdrant vector-store adapter for collection creation, payload indexes, deterministic point upsert, filtered search, scoped deletion, count, and health
- [x] 4.4 Implement manifest compatibility checks that reject model, dimension, distance, normalization, or payload-schema mismatches
- [x] 4.5 Implement candidate collection rebuild, count and sampled-lineage validation, smoke search, atomic alias activation, rollback, retention, and reconciliation
- [x] 4.6 Add in-memory Qdrant integration tests for retry idempotency, incompatible manifests, filtered retrieval, orphan cleanup, failed rebuild isolation, alias activation, and rollback

## 5. Resumable Ingestion Lifecycle

- [x] 5.1 Implement the durable ingestion state machine from receipt through parsing, normalization, chunking, embedding, indexing, validation, and readiness
- [x] 5.2 Implement stage-level idempotency, progress counters, safe diagnostics, bounded batch processing, and retry from the last valid durable boundary
- [x] 5.3 Implement changed-fingerprint invalidation so parser, chunker, or embedding changes rerun only affected downstream stages
- [x] 5.4 Implement document replacement and tombstone flows that exclude obsolete versions from active retrieval before retiring derived index entries
- [x] 5.5 Add failure-injection tests for parser errors, invalid vectors, interrupted upserts, retry, replacement, and scoped deletion

## 6. Hybrid Evidence Retrieval

- [x] 6.1 Refactor the current FTS5/BM25 and herb/compound/SMILES scoring into a lexical retrieval channel without changing lexical-only regression results
- [x] 6.2 Implement vector query embedding and Qdrant candidate retrieval with mandatory ownership, ready-state, active-version, and metadata filters
- [x] 6.3 Implement deterministic Reciprocal Rank Fusion with stable tie-breaking and exact DOI/SMILES post-fusion boosts
- [x] 6.4 Resolve fused chunk IDs through the canonical repository and discard unauthorized, tombstoned, or broken-lineage candidates
- [x] 6.5 Extend Evidence results with immutable document/version/chunk lineage and sanitized retrieval diagnostics while preserving existing Agent result fields
- [x] 6.6 Add retrieval tests for semantic-only matches, exact identifiers, deterministic order, cross-project isolation, broken lineage, vector degradation, and unchanged seven-node proposal/review behavior

## 7. Internal Management APIs and Runtime Integration

- [x] 7.1 Add authenticated APIs to submit ingestion, inspect jobs, list document versions, tombstone documents, and request document reprocessing
- [x] 7.2 Add authenticated APIs for index health/manifests, asynchronous rebuild, rollback, reconciliation, and retrieval diagnostics
- [x] 7.3 Require idempotency keys and document/index permissions for mutation APIs and ensure credentials and full external payloads are absent from logs and audit records
- [x] 7.4 Keep `search_literature` and the seven-node LangGraph workflow backward compatible while exposing retrieval mode and degradation diagnostics
- [x] 7.5 Add API tests for authentication, authorization scope, validation, idempotency, accepted asynchronous jobs, status, deletion, rebuild, and degraded mode

## 8. Migration, Deployment, and Operations

- [x] 8.1 Add a repeatable migration command that imports the existing spreadsheet into canonical records and verifies mappings for every legacy Evidence ID
- [x] 8.2 Add Qdrant to local Docker Compose with persistent storage, health checks, private service networking, and documented optional/required modes
- [x] 8.3 Update environment examples and Agent documentation for local lexical-only operation, local Qdrant, embedding model setup, rebuild, rollback, reconciliation, and troubleshooting
- [x] 8.4 Add operational metrics and structured logs for ingestion stage latency, queue depth, embedding calls, index counts, retrieval channels, degraded mode, and reconciliation drift
- [x] 8.5 Add a shadow-mode comparison command that records lexical and hybrid diagnostics without changing Agent-visible results

## 9. Evaluation and Final Verification

- [x] 9.1 Build a versioned retrieval evaluation fixture covering herbs, compounds, SMILES, multilingual semantic queries, irrelevant near-matches, deletions, and permission boundaries
- [x] 9.2 Define and record baseline lexical and candidate hybrid metrics before enabling hybrid retrieval by default
- [x] 9.3 Run the migration against the real literature file and verify 131 imported records, legacy citation resolution, vector point counts, and deterministic repeated execution
- [x] 9.4 Run all Python tests, Ruff format/check, strict mypy, lock-file validation, Go tests, OpenAPI/YAML parsing, OpenSpec strict validation, and git diff checks
- [x] 9.5 Document the rollout gate, default-off feature flag, rollback procedure, known limitations, and exact file responsibilities for the iteration summary
