from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LiteratureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str
    title: str | None = None
    link_or_doi: str | None = None
    year: int | None = None
    country: str | None = None
    authors: str | None = None
    first_affiliation: str | None = None
    herbs: str | None = None
    compounds: str | None = None
    small_molecule_smiles: list[str] = Field(default_factory=list, max_length=4)
    metal_ions: str | None = None
    organic_macromolecules: str | None = None
    decoction_composition: str | None = None
    assembly_composition: str | None = None
    assembly_morphology: str | None = None
    assembly_phase: str | None = None
    solvent_type: str | None = None
    ph: str | None = None
    temperature: str | None = None
    interaction_types: str | None = None
    interaction_sites: str | None = None
    average_size: str | None = None
    pdi: str | None = None
    zeta_potential: str | None = None
    cac_cmc: str | None = None
    tgel: str | None = None
    clinical_problem: str | None = None
    pharmacodynamic_indicators: str | None = None
    efficacy_comparison: str | None = None
    mechanism: str | None = None
    remarks: str | None = None
    source_file: str
    sheet: str
    source_row: int = Field(ge=2)


class DataQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    total_rows: int = Field(ge=0)
    imported_rows: int = Field(ge=0)
    missing_title: int = Field(ge=0)
    missing_link_or_doi: int = Field(ge=0)
    missing_herb: int = Field(ge=0)
    missing_compounds: int = Field(ge=0)
    rows_with_smiles: int = Field(ge=0)
    field_coverage: dict[str, float]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str


class LiteratureSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str | None = None
    research_goal: str | None = None
    herbs: list[str] = Field(default_factory=list)
    compounds: list[str] = Field(default_factory=list)
    smiles: list[str] = Field(default_factory=list)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)
    project_id: str | None = Field(default=None, min_length=1, max_length=128)
    retrieval_mode: str | None = Field(default=None, pattern=r"^(disabled|optional|required)$")
    diagnostics: bool = False
    top_k: int = Field(default=10, ge=1, le=100)


class LiteratureSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str
    title: str | None = None
    link_or_doi: str | None = None
    year: int | None = None
    source_row: int
    herbs: str | None = None
    compounds: str | None = None
    smiles: list[str]
    conditions: dict[str, str | None]
    final_score: float
    channel_scores: dict[str, float]
    matched_fields: list[str]
    snippet: str | None = None
    canonical_document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    source_locator: dict[str, object] | None = None
    retrieval_diagnostics: dict[str, object] | None = None


class LiteratureSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: LiteratureSearchInput
    hits: list[LiteratureSearchHit]
    total_candidates: int = Field(ge=0)
    source_sha256: str
    degraded: bool = False
