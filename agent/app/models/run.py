from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.proposal import ExperimentProposal, ProposalReview


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LLMStatus(StrEnum):
    DISABLED = "disabled"
    GENERATED = "generated"
    DEGRADED = "degraded"


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    user_id: int
    trace_id: str = Field(min_length=1)
    herbs: list[str] = Field(min_length=1)
    research_goal: str | None


class Evidence(BaseModel):
    evidence_id: str
    source: str
    source_type: str
    reference: str
    retrieved_at: datetime | None = None
    title: str | None = None
    link: str | None = None
    year: int | None = None
    source_row: int | None = None
    matched_fields: list[str] = Field(default_factory=list)
    score: float | None = None
    conditions: dict[str, str | None] | None = None
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    source_locator: dict[str, object] | None = None
    retrieval_diagnostics: dict[str, object] | None = None


class ClaimEvidence(BaseModel):
    claim_id: str
    claim_text: str
    claim_type: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    basis: str


class RuleHit(BaseModel):
    rule_id: str
    description: str
    status: str
    points: int
    observed: str | float | int | None


class CandidateScore(BaseModel):
    rules: list[RuleHit]
    total_score: int
    candidate_threshold: int
    is_candidate: bool


class MolecularDescriptors(BaseModel):
    molecular_weight: float | None = None
    logp: float | None = None
    tpsa: float | None = None
    hbd: int | None = None
    hba: int | None = None


class CompoundResult(BaseModel):
    compound_id: str
    name: str
    herb: str
    smiles: str | None
    pubchem_cid: int | None = None
    descriptors: MolecularDescriptors
    candidate_score: CandidateScore
    evidence_ids: list[str]


class AnalysisSummary(BaseModel):
    herb_count: int
    compound_count: int
    candidate_count: int
    unresolved_herbs: list[str]


class Capability(BaseModel):
    status: str
    detail: str


class WorkflowStep(BaseModel):
    node: str
    status: str
    started_at: datetime
    completed_at: datetime
    detail: str


class ToolingMetadata(BaseModel):
    skills: list[str]
    audit_ids: list[str]


class WorkflowMetadata(BaseModel):
    engine: str = "langgraph"
    thread_id: str
    checkpoint_backend: str = "sqlite"
    status: WorkflowStatus
    steps: list[WorkflowStep]
    tooling: ToolingMetadata | None = None


class AnalysisResult(BaseModel):
    schema_version: str
    normalized_herbs: list[str]
    compounds: list[CompoundResult]
    summary: AnalysisSummary
    capabilities: dict[str, Capability]
    evidence: list[Evidence]
    claims: list[ClaimEvidence] = Field(default_factory=list)
    proposal: ExperimentProposal | None = None
    proposal_review: ProposalReview | None = None
    workflow: WorkflowMetadata | None = None
    retrieval_mode: str | None = None
    retrieval_diagnostics: list[dict[str, object]] = Field(default_factory=list)
    llm_summary: str | None = None
    llm_status: LLMStatus = LLMStatus.DISABLED


class RunResponse(RunCreate):
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    analysis_result: AnalysisResult | None = None
    error_message: str | None = None
    workflow: WorkflowMetadata | None = None


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
