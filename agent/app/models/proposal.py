from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceSourceType = Literal["literature", "computed", "seed", "exploratory_default"]
ReviewSeverity = Literal["info", "warning", "error", "critical"]
ReviewStatus = Literal["approved", "needs_revision", "rejected"]


class ConditionValue(BaseModel):
    """A condition value that never disguises unparsed source text as a number."""

    model_config = ConfigDict(extra="forbid", strict=True)

    raw_text: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    parsed: bool = False
    from_literature: bool

    @model_validator(mode="after")
    def validate_parsing(self) -> ConditionValue:
        if self.parsed and self.value is None:
            raise ValueError("parsed condition values require a numeric value")
        if not self.parsed and (self.value is not None or self.unit is not None):
            raise ValueError("unparsed condition values cannot contain numeric value or unit")
        return self


class SelectedCompound(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    compound_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    herb: str = Field(min_length=1)
    candidate_score: int = Field(ge=0)
    candidate_threshold: int = Field(ge=0)
    is_candidate: bool
    evidence_ids: list[str] = Field(min_length=1)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    hypothesis_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    claims_literature_support: bool = False


class ConditionCell(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    condition_id: str = Field(min_length=1)
    solvent: ConditionValue | None = None
    ph: ConditionValue | None = None
    temperature: ConditionValue | None = None
    concentration_or_ratio: ConditionValue | None = None
    assembly_method: ConditionValue | None = None
    source_type: EvidenceSourceType
    evidence_ids: list[str] = Field(min_length=1)
    literature_supported: bool

    @model_validator(mode="after")
    def validate_nonempty(self) -> ConditionCell:
        values = (
            self.solvent,
            self.ph,
            self.temperature,
            self.concentration_or_ratio,
            self.assembly_method,
        )
        if not any(value is not None for value in values):
            raise ValueError("a condition cell must contain at least one condition")
        return self


class MeasurementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    measurement_id: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    method: str = Field(min_length=1)
    unit: str | None = None
    raw_schedule_text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ControlGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    control_id: str = Field(min_length=1)
    control_type: Literal["blank", "negative", "positive", "vehicle"]
    description: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    risk_id: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ExperimentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    proposal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    selected_compounds: list[SelectedCompound] = Field(min_length=1)
    hypotheses: list[Hypothesis] = Field(min_length=1)
    condition_matrix: list[ConditionCell] = Field(min_length=1)
    measurement_plan: list[MeasurementPlan]
    controls: list[ControlGroup]
    risks: list[RiskItem] = Field(default_factory=list)
    safety_disclaimer: str
    research_disclaimer: str


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    severity: ReviewSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: ReviewStatus
    score: int = Field(ge=0, le=100)
    issues: list[ReviewIssue]
    checked_rules: list[str] = Field(min_length=1)


class ProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    proposal: ExperimentProposal
    review: ProposalReview
