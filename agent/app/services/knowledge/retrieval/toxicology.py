from __future__ import annotations

import logging
from typing import Any, cast

from app.core.config import Settings
from app.models.knowledge import OwnershipScope
from app.models.tooling import SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput
from app.services.knowledge.retrieval.hybrid import HybridRetriever
from app.services.knowledge.storage.factory import (
    VectorRuntime,
    build_lexical_store,
    get_vector_runtime,
)
from app.services.knowledge.storage.mysql_repository import MySQLCanonicalRepository

logger = logging.getLogger(__name__)


def _int_setting(settings: Settings, name: str, default: int) -> int:
    value = getattr(settings, name, default)
    return value if isinstance(value, int) else default


def _str_setting(settings: Settings, name: str, default: str) -> str:
    value = getattr(settings, name, default)
    return value if isinstance(value, str) else default


TOXICOLOGY_RESULT_LIMIT = 5
TOXICOLOGY_FIELD_MAX_CHARS = 200
TOXICOLOGY_COMPOUND_LIMIT = 5
TOXICOLOGY_HERB_FIELDS = (
    "name",
    "common_name",
    "virulence",
    "toxicity_mechanism",
    "symptom_contraindications",
    "adr",
    "clinical_suggestion",
    "clinical_suggestion_basis",
    "link_to_clinical_suggestion",
)


def _truncate(value: Any) -> Any:
    if not isinstance(value, str) or len(value) <= TOXICOLOGY_FIELD_MAX_CHARS:
        return value
    return f"{value[:TOXICOLOGY_FIELD_MAX_CHARS]}…"


def search_toxicology(
    request: SearchMedicalKnowledgeInput,
    settings: Settings,
    *,
    repository: MySQLCanonicalRepository | None = None,
    vector_runtime: VectorRuntime | None = None,
) -> SearchMedicalKnowledgeOutput:
    result_limit = min(request.limit, TOXICOLOGY_RESULT_LIMIT)
    repository = repository or MySQLCanonicalRepository()
    scope = OwnershipScope(
        tenant_id=settings.evidence_tenant_id,
        project_id=settings.evidence_project_id,
    )
    lexical_store = build_lexical_store(settings, repository)
    vector = vector_runtime or get_vector_runtime()
    vector_store = vector.store if settings.vector_mode != "disabled" else None
    expected_snapshot = vector.manifest.source_snapshot if vector.manifest is not None else None
    retriever = HybridRetriever(
        repository,
        vector.embedding,
        vector_store,
        settings.qdrant_collection_alias,
        rrf_k=_int_setting(settings, "fusion_rrf_k", 60),
        policy_version=_str_setting(settings, "fusion_policy_version", "rrf-v1"),
    )
    try:
        hybrid = retriever.search_identifiers(
            request.query,
            scope,
            lexical_store,
            limit=result_limit,
            lexical_limit=_int_setting(settings, "lexical_candidate_limit", result_limit * 2),
            vector_limit=_int_setting(settings, "vector_candidate_limit", result_limit * 2),
            filters=_structured_filters(request.types),
            expected_snapshot=expected_snapshot,
        )
    except RuntimeError as exc:
        raise RuntimeError("toxicology search failed: no retrieval backend available") from exc
    if hybrid.degraded:
        logger.warning("Toxicology retrieval degraded: %s", hybrid.diagnostics)

    results: list[dict[str, Any]] = []
    if hybrid.identifiers:
        by_reference: dict[str, dict[str, Any]] = {}
        for raw in repository.toxicology_records(hybrid.identifiers):
            compounds = cast(list[dict[str, Any]], raw.get("toxic_compounds", []))
            herb = {
                field: _truncate(raw[field])
                for field in TOXICOLOGY_HERB_FIELDS
                if raw.get(field) is not None
            }
            herb["toxic_compounds"] = [
                {
                    key: _truncate(value)
                    for key, value in dict(compound).items()
                    if key != "herb_id" and value is not None
                }
                for compound in compounds[:TOXICOLOGY_COMPOUND_LIMIT]
            ]
            by_reference[str(raw["reference"])] = herb
        results = [by_reference[item] for item in hybrid.identifiers if item in by_reference]
    return SearchMedicalKnowledgeOutput(results=results, diagnostics=hybrid.diagnostics)


def _structured_filters(types: list[str]) -> dict[str, object] | None:
    """Keep the public `types` input compatible while accepting explicit key:value filters."""
    filters: dict[str, object] = {}
    for item in types:
        key, separator, value = item.partition(":")
        if separator and key in {"herb_id", "reference", "source_snapshot"} and value:
            filters[key] = int(value) if key == "herb_id" and value.isdigit() else value
    return filters or None
