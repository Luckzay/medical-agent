## Context

See `proposal.md` for motivation. The Agent currently imports 131 structured Excel literature rows, stores them in SQLite, and retrieves them with FTS5/BM25 plus deterministic herb, compound, and SMILES boosts. `search_literature` is executed through the shared Tool Runtime inside the seven-node LangGraph workflow. Existing tests require offline, deterministic behavior, and existing Evidence IDs feed proposal generation and independent review.

The next data sources will include both structured rows and long-form documents. The design therefore separates canonical source truth, lexical indexes, vector indexes, and generated Agent state. A vector database is an index, not the authoritative document store.

## Goals / Non-Goals

**Goals:**

- Establish durable document, version, chunk, ingestion-job, and index-manifest records before adding many formats.
- Make parsing, chunking, embedding, and indexing independently versioned and reproducible.
- Provide safe incremental maintenance: deduplicate, upsert, replace, delete, retry, reconcile, rebuild, atomically activate, and roll back.
- Introduce Qdrant behind a store interface and hybrid retrieval without breaking SQLite FTS5 or the current Agent contract.
- Keep local development and the complete test suite deterministic and network-free.
- Preserve immutable source lineage from every retrieved chunk through Evidence, Claim, Proposal, and Reviewer output.

**Non-Goals:**

- Building OCR, image understanding, formula recognition, or production parsers for every file type in the first implementation.
- Treating generated summaries as primary evidence.
- Replacing the current workflow with an autonomous planner.
- Making a single embedding model permanent; model replacement is handled as a new index generation.
- Using the vector database as the source of truth for documents or permissions.

## Decisions

### 1. Canonical metadata stays in SQLite initially; Qdrant is a replaceable derived index

Add canonical tables for `documents`, `document_versions`, `document_blocks`, `document_chunks`, `ingestion_jobs`, `embedding_cache`, and `index_manifests` to the Agent data layer. Original files remain referenced by a source URI and content hash; future object storage can implement the same source-artifact contract. Qdrant stores vectors and retrieval payload only.

This keeps the first implementation compatible with the existing local-first service and gives deletion, retries, and historical citations a transactional source of truth. Moving canonical tables to PostgreSQL later does not change parsers, chunkers, or Qdrant point identities. Storing everything only in Qdrant was rejected because payloads do not provide the lifecycle, relational lineage, and immutable history required by the Agent.

### 2. Use explicit logical-document and immutable-version identities

`document_id` identifies a logical source inside `tenant_id` and `project_id`. `version_id` is derived from document identity and source SHA-256. An unchanged import returns the existing version. Changed content creates a new immutable version; activation occurs only after all required indexes validate. Historical evidence continues to resolve against prior versions.

Legacy Excel rows are represented as structured child documents or structured blocks under a dataset version. A compatibility mapping preserves IDs such as `literature:EN:90`. Existing Agent outputs therefore remain valid while gaining canonical `document_id`, `version_id`, and `chunk_id` lineage.

### 3. Parser and chunker registries use normalized blocks as their boundary

A parser produces ordered normalized blocks rather than one flattened string. Blocks carry a type (`heading`, `paragraph`, `table`, `structured_row`, `caption`, or `code`), hierarchy, source locator, language, and warnings. The initial adapters cover the existing Excel importer plus plain text and Markdown; PDF and Word adapters can be registered without changing indexing.

A chunker consumes blocks and a versioned `ChunkingPolicy`. The default policy is structure-first: never split a structured row or small table; keep headings with following content; only split an oversized textual section. The initial text budget is 700 tokens with 100-token overlap, configurable per document type. These are safe defaults, not quality claims; policy identity and actual token count are persisted so evaluation can replace them.

Each chunk ID is a UUIDv5 over ownership scope, version ID, chunker fingerprint, ordered source locator, and content hash. Parent context is stored separately, allowing small retrieval chunks and larger context expansion without duplicating citation identity.

Fixed character slicing was rejected because it separates conditions from units, headings from methods, and table cells from headers.

### 4. Qdrant uses versioned physical collections and a stable read alias

Use Qdrant as the first production vector backend because it supports filtered ANN search, payload indexes, deterministic point upserts, collection aliases, local Docker operation, and an in-memory client mode for integration tests. A `VectorStore` port prevents Qdrant types from leaking into Evidence and workflow models.

Physical collections follow `medical_evidence_v{schema}_{generation}` and a stable alias such as `medical_evidence_active` serves reads. A manifest records vector name, dimension, cosine distance, embedding fingerprint, payload schema, build snapshot, point counts, and status. Reindex creates a candidate collection, creates payload indexes, upserts all eligible chunks, validates counts and sampled lineage, runs retrieval smoke tests, and only then swaps the alias. The previous healthy generation is retained for rollback and retired by policy.

Point IDs are deterministic UUIDs over tenant, project, version, chunk, vector name, and embedding fingerprint. Payload includes only filter and resolution fields: tenant/project, document/version/chunk IDs, status, source type, language, herbs, compounds, SMILES, content hash, and index generation. Canonical chunk text is resolved from the metadata store; a bounded excerpt may be included for debugging but is not source truth.

### 5. Embeddings are provider-neutral and fingerprinted

Define an `EmbeddingProvider` port with `embed_documents`, `embed_query`, `dimension`, `fingerprint`, and `health`. The fingerprint includes provider, model revision, dimension, normalization, instruction template, and tokenizer/chunk-policy compatibility. Vectors are cached by chunk content hash plus fingerprint.

The first real local provider should use a configurable multilingual model rather than hard-code a scientific claim about one model. `intfloat/multilingual-e5-small` is the proposed development default because it is multilingual and relatively small; production selection remains configuration and must be evaluated on the project retrieval set. A deterministic hash-based provider is allowed only in tests and is clearly identified as non-semantic. External providers use the same contract and never persist credentials or full request payloads.

Random mock vectors were rejected because they make ranking tests unstable. Eagerly loading a model during application import was rejected because it would break offline startup and API-only operations.

### 6. Ingestion is a resumable state machine with durable boundaries

An ingestion job progresses through `received`, `parsing`, `normalized`, `chunked`, `embedded`, `indexed`, `quality_checked`, and `ready`, with `failed`, `deleting`, and `deleted` terminal or recovery states. Stage outputs are committed before transition. A retry resumes from the last valid stage when fingerprints are unchanged; otherwise it invalidates downstream products and restarts from the earliest affected stage.

Idempotency is based on tenant, project, logical source identity, source hash, parser fingerprint, chunker fingerprint, and embedding fingerprint. Batch embedding and upsert use bounded sizes, timeout, retry with jitter, and progress counters. Reconciliation compares ready canonical chunks with active Qdrant points and FTS rows, removing orphans only within the requested ownership scope.

The first implementation can execute jobs using the existing Agent executor; the service boundary is compatible with a later Redis Streams or NATS worker without changing job semantics.

### 7. Hybrid retrieval uses independent channels and deterministic RRF

Keep existing FTS5/BM25 and scientific field boosts as the lexical channel. The vector channel embeds the normalized query and retrieves a larger candidate pool using mandatory ownership and active-version filters. Both channels return canonical chunk IDs; unresolved or unauthorized IDs are discarded.

Fuse channel ranks with Reciprocal Rank Fusion using a versioned constant and deterministic chunk-ID tie break. Exact DOI and SMILES matches remain explicit boosts after fusion because semantic similarity must not weaken exact scientific identifiers. Return diagnostics containing channel ranks, fusion policy, active manifest, embedding fingerprint, latency, and degraded reason. Downstream nodes continue receiving compatible Evidence objects, not raw vector-store hits.

A weighted sum of raw BM25 and cosine scores was rejected because score distributions are not directly comparable and vary by corpus and embedding model.

### 8. Management APIs are internal, authenticated, and asynchronous where necessary

Add internal endpoints to submit an ingestion job, inspect a job, list document versions, tombstone a document, request reprocessing, request a full index rebuild, inspect index health/manifests, and execute retrieval diagnostics. Expensive ingestion and reindex requests return a job identifier rather than holding an HTTP request open. Mutation endpoints require idempotency keys and appropriate document/index permissions.

Initial API scope:

- `POST /internal/v1/documents/ingestions`
- `GET /internal/v1/ingestions/{job_id}`
- `GET /internal/v1/documents/{document_id}/versions`
- `DELETE /internal/v1/documents/{document_id}`
- `POST /internal/v1/documents/{document_id}/reprocess`
- `GET /internal/v1/evidence/indexes/status`
- `POST /internal/v1/evidence/indexes/rebuild`
- `POST /internal/v1/evidence/search/diagnostics`

The existing quality and literature search endpoints remain supported.

### 9. Configuration has explicit modes and safe startup behavior

Add settings for vector mode (`disabled`, `optional`, `required`), Qdrant URL/API key/collection alias/timeouts, embedding provider/model/revision/device/batch size, chunk policy, candidate sizes, fusion policy, and ingestion worker limits. Defaults preserve offline lexical behavior. In `required` mode, readiness fails if Qdrant or the embedding provider is incompatible; in `optional` mode, readiness reports degraded but the service starts.

Secrets are loaded through settings and excluded from logs, audit payloads, manifests, and Qdrant payloads.

## Risks / Trade-offs

- [A new vector service increases operational complexity] → Keep it optional locally, provide health/manifests, Docker configuration, alias-based rebuilds, and lexical degradation.
- [Embedding model changes can silently corrupt similarity] → Fingerprint every vector and reject writes to incompatible collection manifests.
- [Chunk defaults may perform poorly on scientific documents] → Persist policy versions, create a retrieval evaluation set, and change policy only through a rebuildable generation.
- [Dual indexes can drift] → Treat canonical chunks as truth, add reconciliation, sampled lineage validation, and readiness gates.
- [Deletion conflicts with historical reproducibility] → Remove deleted content from active search while retaining minimal immutable citation lineage under explicit retention policy.
- [Large local models make installation heavy] → Keep model dependencies optional, lazy-load providers, and use deterministic providers only for tests.
- [Existing literature ranking may change unexpectedly] → Preserve lexical-only defaults until hybrid evaluation passes and gate vector fusion behind configuration.
- [Qdrant payload filters can be missed by a caller] → Build authorization filters inside the retrieval repository, not in routes or Agent prompts.

## Migration Plan

1. Add canonical lifecycle tables and models behind feature flags, with no retrieval behavior change.
2. Import the existing Excel dataset into canonical document/version/block/chunk records and verify all 131 legacy Evidence IDs map to immutable lineage.
3. Add deterministic test embeddings and an isolated Qdrant integration backend; keep production vector mode disabled by default.
4. Add real embedding and Qdrant providers, create a candidate collection, and index canonical ready chunks.
5. Run count, lineage, deletion, exact-identifier, and retrieval regression checks. Compare hybrid retrieval against the existing fixed query set.
6. Enable vector retrieval in optional shadow mode, recording diagnostics without changing Agent results.
7. Activate hybrid fusion after evaluation thresholds pass; preserve a configuration switch to lexical-only mode.
8. Roll back by changing the read alias to the prior collection and setting vector mode to disabled. Canonical metadata and FTS remain usable throughout.

## Open Questions

- The production embedding model and final chunk-policy parameters will be selected using the retrieval evaluation set; changing either creates a new manifest generation and does not alter this architecture.
- Object storage is intentionally behind a source-artifact interface. Local files are sufficient for this iteration; S3/MinIO can be selected when binary upload APIs are implemented.
