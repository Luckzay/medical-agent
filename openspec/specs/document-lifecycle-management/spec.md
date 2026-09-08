# document-lifecycle-management Specification

## Purpose
Defines a sustainable, auditable lifecycle for heterogeneous source documents so that every indexed chunk and retrieved evidence item remains reproducible and traceable as content, parsers, and splitting policies evolve.
## Requirements
### Requirement: Canonical document identity and immutable versions
The system SHALL represent a logical document with a stable document identity and SHALL create an immutable version for each distinct source content hash. A version SHALL retain its source location, media type, source hash, parser identity, parsing status, ownership scope, and creation time.

#### Scenario: Re-import unchanged content
- **WHEN** an authorized caller imports a source whose content hash already exists for the same logical document
- **THEN** the system returns the existing version and does not duplicate its chunks or index entries

#### Scenario: Import changed content
- **WHEN** an authorized caller imports changed content for an existing logical document
- **THEN** the system creates a new immutable version while preserving the previous version and its historical citations

### Requirement: Extensible parser selection
The system SHALL select a registered parser by media type and SHALL reject unsupported or ambiguous inputs with a machine-readable error. Parsed output SHALL preserve headings, paragraphs, tables, structured rows, captions, page or source-row positions, and parser warnings when those elements are available.

#### Scenario: Supported document is parsed
- **WHEN** a caller imports a supported document type
- **THEN** the system produces normalized structural blocks with source locations and parser provenance

#### Scenario: Unsupported document is submitted
- **WHEN** a caller imports a document for which no parser is registered
- **THEN** the ingestion job fails without indexing partial content and reports the unsupported media type

### Requirement: Structure-aware deterministic chunking
The system SHALL split normalized blocks using a versioned chunking policy that respects structural boundaries before token limits. Every chunk SHALL have a deterministic identity, ordered position, source locator, parent context reference, content hash, token count, chunker version, and document-version reference.

#### Scenario: Same version is chunked twice
- **WHEN** the same document version is processed twice with the same chunking policy
- **THEN** the system produces the same ordered chunk identities and content hashes

#### Scenario: Table is chunked
- **WHEN** a parsed block is a table or structured spreadsheet row
- **THEN** the system preserves headers, units, row provenance, and the relation between cells instead of truncating the block as plain text

#### Scenario: Oversized section is chunked
- **WHEN** a structural section exceeds the configured token budget
- **THEN** the system creates bounded child chunks with configured overlap and links them to retrievable parent context

### Requirement: Auditable ingestion lifecycle
The system SHALL expose an ingestion job state covering receipt, parsing, normalization, chunking, embedding, indexing, quality validation, readiness, failure, and deletion. Each transition SHALL record timestamps, retry count, error code, and the affected document version without storing credentials.

#### Scenario: A stage fails
- **WHEN** parsing, embedding, or indexing fails
- **THEN** the job records the failed stage and a safe diagnostic and can be retried from the last durable boundary

#### Scenario: Content becomes searchable
- **WHEN** all required chunks pass quality validation and active indexes acknowledge the version
- **THEN** the document version transitions to ready and becomes eligible for retrieval

### Requirement: Incremental replacement and deletion
The system SHALL support version activation, logical-document deletion, version deletion subject to citation retention rules, and repeatable reprocessing. Deleted or superseded content SHALL be excluded from new retrieval results and removed from active indexes.

#### Scenario: Active version is replaced
- **WHEN** a new version is successfully indexed and activated
- **THEN** new searches use the new version while historical runs can still resolve citations to the prior version

#### Scenario: Document is deleted
- **WHEN** an authorized caller deletes a logical document
- **THEN** the system tombstones it, removes all of its chunks from active retrieval indexes, and preserves the minimum lineage needed to resolve historical audit records

### Requirement: Existing literature compatibility
The system SHALL migrate existing spreadsheet literature records into the canonical lifecycle while preserving current literature evidence identifiers and current search behavior when vector retrieval is unavailable.

#### Scenario: Existing literature index is migrated
- **WHEN** the current literature spreadsheet is ingested through the new pipeline
- **THEN** every imported row retains a resolvable mapping from its existing evidence identifier to the canonical document version and chunk lineage

