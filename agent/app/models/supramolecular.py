from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OutcomeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"


class SupramolecularSearchFilters(BaseModel):
    """Qdrant 中可直接执行的实验过滤条件。"""

    outcome_status: OutcomeStatus | None = None
    compound_name: str | None = Field(default=None, min_length=1, max_length=512)
    solvent_type: str | None = Field(default=None, min_length=1, max_length=512)
    assembly_morphology: str | None = Field(default=None, min_length=1, max_length=512)
    interaction_type: str | None = Field(default=None, min_length=1, max_length=512)
    metal_ion: str | None = Field(default=None, min_length=1, max_length=512)
    ph_min: float | None = Field(default=None, ge=0, le=14)
    ph_max: float | None = Field(default=None, ge=0, le=14)
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "compound_name",
        "solvent_type",
        "assembly_morphology",
        "interaction_type",
        "metal_ion",
        mode="before",
    )
    @classmethod
    def strip_filter_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_ranges(self) -> SupramolecularSearchFilters:
        if self.ph_min is not None and self.ph_max is not None and self.ph_min > self.ph_max:
            raise ValueError("ph_min must not exceed ph_max")
        if (
            self.temperature_min_c is not None
            and self.temperature_max_c is not None
            and self.temperature_min_c > self.temperature_max_c
        ):
            raise ValueError("temperature_min_c must not exceed temperature_max_c")
        return self


class SupramolecularSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SupramolecularSearchFilters = Field(default_factory=SupramolecularSearchFilters)

    model_config = ConfigDict(extra="forbid")

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class SupramolecularExperimentHit(BaseModel):
    id: int | str
    relevance_score: float = Field(ge=0)

    # 实验结构会随 schema 演进；保留并透传已索引的规范字段。
    model_config = ConfigDict(extra="allow")


class SupramolecularSearchResponse(BaseModel):
    experiments: list[SupramolecularExperimentHit]
    summary: str | None = None
    total: int = Field(ge=0)
