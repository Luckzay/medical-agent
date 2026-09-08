# hybrid-evidence-retrieval Specification

## Purpose
Defines explainable hybrid evidence retrieval that combines exact scientific term matching with semantic recall while enforcing access scope, stable ranking, and complete source citations.
## Requirements
### Requirement: Hybrid candidate retrieval
The system SHALL retrieve lexical and vector candidate sets independently, apply the same eligibility and ownership filters to both, and combine them using a versioned deterministic fusion policy. Exact identifiers such as DOI and SMILES SHALL remain eligible for exact-match boosts.

#### Scenario: Both retrieval channels are healthy
- **WHEN** a query has lexical and vector candidates
- **THEN** the system returns a fused stable ranking with channel ranks and fusion-policy version in diagnostics

#### Scenario: Only one channel is healthy
- **WHEN** either lexical or vector retrieval is unavailable
- **THEN** the system returns results from the healthy channel and explicitly reports the degraded mode

### Requirement: Query and metadata filtering
The system SHALL support normalized query text and filters for tenant, project, document type, source, language, herb, compound, SMILES, document status, and active version. Mandatory authorization filters SHALL be applied inside every retrieval channel before results are returned.

#### Scenario: Cross-project content would otherwise match
- **WHEN** a highly similar chunk belongs to a project outside the caller's authorized scope
- **THEN** it is absent from candidate sets, diagnostics, and returned evidence

### Requirement: Citation-complete evidence results
Every returned result SHALL include an immutable evidence identity, document and version identity, chunk identity, source locator, bounded excerpt, retrieval-channel provenance, and enough metadata to resolve the original source. Derived claims SHALL reference only evidence identities present in the run result.

#### Scenario: A chunk from a paginated document is returned
- **WHEN** retrieval selects a PDF-derived chunk
- **THEN** the evidence includes the source file identity, document version, page or structural locator, and chunk identity

#### Scenario: Historical evidence is resolved
- **WHEN** a historical Agent run references a superseded document version
- **THEN** the system resolves its stored citation to that immutable version rather than silently substituting current content

### Requirement: Deterministic fusion and ranking stability
For identical canonical data, index manifests, query, filters, and retrieval-policy version, the system SHALL produce the same result ordering and scores within documented numeric tolerance. Ties SHALL use stable evidence identities.

#### Scenario: Identical search is repeated
- **WHEN** the same query and filters are executed against unchanged active indexes
- **THEN** returned evidence order and diagnostic ranks remain stable

### Requirement: Retrieval diagnostics and quality controls
Authorized internal callers SHALL be able to inspect sanitized lexical rank, vector rank, fused rank, exact-field matches, active index generation, embedding fingerprint, policy version, latency, and degraded-mode reason. The system SHALL reject or quarantine results whose lineage cannot be resolved.

#### Scenario: Vector point has broken lineage
- **WHEN** a vector candidate does not resolve to an eligible canonical chunk
- **THEN** the candidate is excluded, the inconsistency is reported, and no citation is fabricated

### Requirement: Backward-compatible Agent integration
The existing literature-search tool and seven-node workflow SHALL continue to return current Evidence and Claim–Evidence structures. Hybrid retrieval SHALL be an implementation upgrade that does not require downstream proposal or Reviewer code to accept uncited text.

#### Scenario: Agent runs with vector retrieval disabled
- **WHEN** the Agent executes in offline or degraded mode
- **THEN** the evidence, proposal, review, and finalize nodes complete using compatible lexical evidence behavior

### Requirement: Agent online hybrid evidence retrieval
The system SHALL execute `search_literature` and the LangGraph evidence node through one shared retrieval runtime while preserving legacy request compatibility and resolvable evidence lineage.

#### Scenario: Disabled mode
- **WHEN** vector mode is `disabled`
- **THEN** only FTS5 is queried and legacy ordering is preserved

#### Scenario: Optional vector failure
- **WHEN** vector mode is `optional` and embedding or Qdrant fails
- **THEN** lexical results are returned with a safe degraded reason

#### Scenario: Required vector failure
- **WHEN** vector mode is `required` and embedding or Qdrant is unhealthy
- **THEN** the request fails explicitly without lexical fallback

#### Scenario: Hybrid success
- **WHEN** both channels are healthy
- **THEN** independently recalled candidates are deterministically fused by RRF, exact DOI/SMILES matches are boosted, mandatory scope/status/active-version filters apply, and diagnostics contain lexical/vector/fused ranks

### Requirement: Trusted ownership scope
The system SHALL prefer tenant/project scope supplied by trusted execution context over model-controlled arguments.

#### Scenario: Scope isolation
- **WHEN** a request attempts to name another scope
- **THEN** trusted scope remains effective and no cross-scope candidate is returned

### Requirement: Lazy real provider
The system SHALL NOT load or download the sentence-transformer model during module import or service startup.

#### Scenario: First vector query
- **WHEN** the first enabled vector query executes
- **THEN** the pinned model is loaded and query text receives the E5 query prefix

