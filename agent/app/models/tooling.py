from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.evidence import LiteratureSearchHit, LiteratureSearchInput
from app.models.proposal import ExperimentProposal
from app.models.run import (
    CandidateScore,
    ClaimEvidence,
    CompoundResult,
    Evidence,
    MolecularDescriptors,
)

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)
ToolHandler = Callable[[BaseModel], BaseModel]


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_retries: int = Field(default=0, ge=0, le=3)


class ToolDefinition[InputT: BaseModel, OutputT: BaseModel](BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_model: type[InputT]
    output_model: type[OutputT]
    required_permissions: frozenset[str] = frozenset()
    timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    retry_policy: RetryPolicy = RetryPolicy()
    handler: Callable[[InputT], OutputT]

    def public_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "required_permissions": sorted(self.required_permissions),
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy.model_dump(mode="json"),
        }


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tool_names: tuple[str, ...] = Field(min_length=1)
    context_policy: dict[str, Any]


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    node: str = Field(min_length=1)
    permissions: frozenset[str]


class ToolAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    run_id: str
    node: str
    tool_name: str
    tool_version: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: str
    attempts: int
    error_type: str | None = None
    error_message: str | None = None


class NormalizeHerbsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    herbs: list[str] = Field(min_length=1)


class NormalizeHerbsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    normalized_herbs: list[str]


class DiscoveredCompoundModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compound_id: str
    name: str
    herb: str
    smiles: str
    pubchem_cid: int | None = None
    evidence_ids: list[str]


class DiscoverCompoundsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    normalized_herbs: list[str] = Field(min_length=1)


class DiscoverCompoundsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[DiscoveredCompoundModel]
    evidence: list[Evidence]
    unresolved_herbs: list[str]
    online_failures: int = Field(ge=0)


class DescriptorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compound: DiscoveredCompoundModel


class CalculateDescriptorsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[DiscoveredCompoundModel] = Field(min_length=1)


class DescribedCompound(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compound: DiscoveredCompoundModel
    descriptors: MolecularDescriptors


class CalculateDescriptorsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[DescribedCompound]


class ScoreCandidatesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[DescribedCompound] = Field(min_length=1)


class ScoredCompound(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compound: DiscoveredCompoundModel
    descriptors: MolecularDescriptors
    candidate_score: CandidateScore


class ScoreCandidatesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[ScoredCompound]


class SearchLiteratureInput(LiteratureSearchInput):
    pass


class SearchLiteratureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    hits: list[LiteratureSearchHit]
    total_candidates: int = Field(ge=0)
    source_sha256: str
    degraded: bool = False
    retrieval_mode: Literal["lexical", "hybrid", "hybrid_reranker"] = "lexical"
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    degraded_reason: str | None = None


class SearchMedicalKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=200)
    types: list[
        Literal["herbs", "decoctions", "couplets", "compounds", "papers", "expertises"]
    ] = Field(default_factory=list, max_length=6)
    limit: int = Field(default=10, ge=1, le=50)


class SearchMedicalKnowledgeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[dict[str, Any]] = Field(default_factory=list)


class GenerateExperimentProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compounds: list[CompoundResult] = Field(min_length=1)
    claims: list[ClaimEvidence] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)
    max_conditions: int = Field(default=12, ge=1, le=100)


class ReviewExperimentProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    proposal: ExperimentProposal
    available_evidence_ids: list[str] = Field(min_length=1)
