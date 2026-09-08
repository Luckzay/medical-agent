## ADDED Requirements

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
