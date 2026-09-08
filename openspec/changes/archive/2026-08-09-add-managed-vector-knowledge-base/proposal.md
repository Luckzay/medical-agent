## Why

The current Evidence RAG pipeline is intentionally limited to 131 structured Excel rows indexed with SQLite FTS5. It cannot sustainably ingest, version, split, embed, reindex, or retire the growing set of PDF, Word, Markdown, HTML, spreadsheet, and experimental documents expected by the platform.

This change establishes a managed document and vector knowledge-base foundation before more data sources are introduced, so every retrieved claim remains incrementally maintainable, reproducible, permission-aware, and traceable to an immutable source location.

## What Changes

- Introduce a canonical document model covering logical documents, immutable versions, source artifacts, parser/chunker/embedding provenance, chunks, and evidence locations.
- Add a parser and chunker registry with structure-aware splitting, deterministic chunk identities, parent/child context, token budgets, and format-specific handling for tables and structured rows.
- Add a managed Qdrant vector index with collection schema/version management, payload indexes, health checks, idempotent batch upsert, deletion, rebuild, and alias-based zero-downtime activation.
- Add an embedding-provider abstraction with explicit model identity and dimension, a deterministic offline test provider, batching, retry, timeout, and content-hash reuse.
- Add an asynchronous ingestion lifecycle that supports incremental import, duplicate detection, document replacement, tombstones, reindexing, failure recovery, and per-stage audit state.
- Upgrade evidence retrieval to hybrid lexical/vector retrieval with metadata filtering, deterministic fusion, stable ranking, and complete citation lineage while preserving the current SQLite FTS5 fallback.
- Add authenticated internal management APIs for document status, ingestion, version listing, deletion, reindexing, collection health, and retrieval diagnostics.
- Migrate the existing literature spreadsheet into the canonical document/version/chunk model without invalidating existing LiteratureRecord evidence IDs or the seven-node Agent workflow.
- Preserve a local/offline mode in which tests and baseline development do not require a running Qdrant service or an external embedding API.

## Capabilities

### New Capabilities
- `document-lifecycle-management`: Canonical multi-format document ingestion, versioning, deduplication, structure-aware chunking, lineage, deletion, and reprocessing behavior.
- `managed-vector-index`: Qdrant collection lifecycle, embedding provenance, idempotent indexing, health management, reindexing, and offline fallback behavior.
- `hybrid-evidence-retrieval`: Permission-aware lexical and vector retrieval, deterministic fusion, diagnostics, and citation integrity across structured and unstructured sources.

### Modified Capabilities

None. This repository has no existing OpenSpec capability specifications; compatibility with the current Evidence RAG is defined by the new capability requirements.

## Impact

The primary impact is within the Python Agent service: evidence models and repositories, ingestion services, retrieval, configuration, internal APIs, Tool Runtime integration, tests, dependencies, and container configuration. Qdrant becomes an optional local-development service and the production vector-index dependency; SQLite FTS5 remains available for lexical search and degraded/offline operation.

New persistent state includes canonical document metadata, immutable document versions, chunks, ingestion jobs, index manifests, and Qdrant collections. Existing literature imports, `search_literature`, Evidence IDs, Claim–Evidence bindings, experiment proposals, Reviewer checks, and LangGraph checkpoint behavior must remain backward compatible.
