# managed-vector-index Specification

## Purpose
Defines safe and repeatable management of vector collections and embeddings so indexes can be incrementally maintained, rebuilt, validated, activated, and rolled back without losing source lineage.
## Requirements
### Requirement: Versioned vector index manifest
The system SHALL maintain an index manifest containing collection schema version, active alias, vector names and dimensions, distance metric, embedding provider and model identity, normalization policy, payload schema version, build status, and source snapshot identity.

#### Scenario: Incompatible embedding configuration is requested
- **WHEN** a configured embedding dimension or model fingerprint differs from the active collection manifest
- **THEN** the system refuses to write incompatible points and requires a new collection generation

### Requirement: Deterministic and idempotent point management
Each indexed chunk SHALL map to a deterministic vector point identity derived from tenant scope, document version, chunk identity, vector name, and embedding fingerprint. Repeating the same indexing request SHALL not create duplicate points.

#### Scenario: Batch is retried
- **WHEN** an interrupted upsert batch is submitted again with identical chunks and embedding fingerprint
- **THEN** the resulting vector index contains exactly one current point per chunk

#### Scenario: Chunk content changes
- **WHEN** content or embedding provenance for a chunk changes
- **THEN** the system writes the new deterministic point and removes or deactivates the obsolete active point

### Requirement: Managed collection lifecycle
The system SHALL support collection creation, payload-index creation, health inspection, incremental synchronization, full rebuild, validation, alias-based activation, rollback, and retirement. A rebuild SHALL not replace the active collection until validation succeeds.

#### Scenario: Rebuild succeeds
- **WHEN** a candidate collection has the expected point count, schema, sample lineage, and retrieval smoke-test results
- **THEN** the system atomically activates the candidate through the stable read alias

#### Scenario: Rebuild validation fails
- **WHEN** candidate validation detects missing points, incompatible schema, or broken lineage
- **THEN** the active alias remains unchanged and the candidate is marked failed

#### Scenario: Rollback is requested
- **WHEN** an authorized caller rolls back to the previous healthy generation
- **THEN** the read alias atomically targets that generation without re-embedding source documents

### Requirement: Embedding provider contract and provenance
The system SHALL access embeddings through a provider-neutral contract supporting document and query embeddings, batching, timeout, retry, dimension validation, and health reporting. Every stored vector SHALL retain a reproducible embedding fingerprint; secrets and complete external request payloads SHALL NOT be persisted.

#### Scenario: Cached content is encountered
- **WHEN** a chunk content hash and embedding fingerprint have already produced a valid vector
- **THEN** the system reuses the vector instead of invoking the provider again

#### Scenario: Provider returns an invalid vector
- **WHEN** an embedding response has an unexpected count, dimension, or non-finite value
- **THEN** the indexing stage fails safely and no incompatible point is activated

### Requirement: Degraded and offline operation
The system SHALL expose vector-index availability separately from lexical-index availability. If the vector service or embedding provider is unavailable, existing lexical evidence search SHALL remain functional and the response SHALL identify degraded retrieval mode.

#### Scenario: Vector service is unavailable
- **WHEN** a search is executed while the vector index is unhealthy
- **THEN** the system returns lexical results with degraded-mode diagnostics instead of fabricating vector scores or failing the entire Agent run

#### Scenario: Offline tests execute
- **WHEN** the automated test suite runs without network access or downloaded model weights
- **THEN** deterministic test embeddings and an isolated vector-store test backend validate lifecycle behavior reproducibly

### Requirement: Scoped deletion and reconciliation
The system SHALL delete vector points by tenant, project, document, version, or index generation and SHALL reconcile manifest counts against canonical ready chunks.

#### Scenario: Reconciliation finds orphan points
- **WHEN** the active collection contains points with no eligible canonical chunk
- **THEN** the system reports and removes those points without altering valid points from other ownership scopes

