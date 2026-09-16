from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.knowledge import OwnershipScope
from app.models.tooling import (
    NormalizeHerbsInput,
    NormalizeHerbsOutput,
    RetryPolicy,
    SearchMedicalKnowledgeInput,
    SearchMedicalKnowledgeOutput,
    ToolDefinition,
)
from app.services.analysis_service import AnalysisService
from app.services.hybrid_retrieval import reciprocal_rank_fusion
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.runtime import get_vector_runtime
from app.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

TOXICOLOGY_RESULT_LIMIT = 5
TOXICOLOGY_FIELD_MAX_CHARS = 200
TOXICOLOGY_COMPOUND_LIMIT = 5
TOXICOLOGY_HERB_FIELDS = (
    "name",
    "common_name",
    "reference",
    "virulence",
    "toxicity_mechanism",
    "symptom_contraindications",
    "adr",
    "clinical_suggestion",
    "clinical_suggestion_basis",
    "link_to_clinical_suggestion",
)


def _truncate_toxicology_value(value: Any) -> Any:
    if not isinstance(value, str) or len(value) <= TOXICOLOGY_FIELD_MAX_CHARS:
        return value
    return f"{value[:TOXICOLOGY_FIELD_MAX_CHARS]}…"


TOOL_VERSION = "1.3.1"
INTERNAL_TOOL_PERMISSIONS = frozenset(
    {
        "herbs:normalize",
        "knowledge:search",
    }
)
MCP_TOOL_PERMISSIONS = INTERNAL_TOOL_PERMISSIONS


def build_tool_registry(
    analysis: AnalysisService
) -> ToolRegistry:
    registry = ToolRegistry()
    settings = get_settings()

    def normalize(request: NormalizeHerbsInput) -> NormalizeHerbsOutput:
        return NormalizeHerbsOutput(normalized_herbs=analysis.normalize(request.herbs))

    def search_medical_knowledge(
        request: SearchMedicalKnowledgeInput,
    ) -> SearchMedicalKnowledgeOutput:
        response = httpx.post(
            settings.knowledge_api_url,
            json=request.model_dump(mode="json"),
            headers={"X-Agent-Token": settings.internal_token},
            timeout=settings.knowledge_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            payload = {"results": payload}
        return SearchMedicalKnowledgeOutput.model_validate(payload)

    def search_toxicology_knowledge(
        request: SearchMedicalKnowledgeInput,
    ) -> SearchMedicalKnowledgeOutput:
        result_limit = min(request.limit, TOXICOLOGY_RESULT_LIMIT)
        lexical_ids: list[str] = []
        exact_boosts: dict[str, tuple[str, ...]] = {}

        canonical = SQLiteCanonicalRepository(settings.canonical_database_path)
        scope = OwnershipScope(
            tenant_id=settings.evidence_tenant_id,
            project_id=settings.evidence_project_id,
        )

        # 1. Lexical search (SQLite)
        sqlite_failed = False
        try:
            # Exact match (Herb name)
            rows = canonical.connection.execute(
                "SELECT reference FROM toxicology_herbs WHERE name = ?",
                (request.query,)
            ).fetchall()
            for row in rows:
                ref = str(row["reference"])
                if ref not in exact_boosts:
                    lexical_ids.append(ref)
                    exact_boosts[ref] = ("name",)

            # Exact match (Compound name, CAS, Formula)
            rows = canonical.connection.execute(
                "SELECT h.reference FROM toxicology_herbs h "
                "JOIN toxicology_compounds c ON h.herb_id = c.herb_id "
                "WHERE c.name = ? OR c.cas = ? OR c.formula = ?",
                (request.query, request.query, request.query)
            ).fetchall()
            for row in rows:
                ref = str(row["reference"])
                if ref not in exact_boosts:
                    lexical_ids.append(ref)
                    exact_boosts[ref] = ("compound",)

            # FTS match (Safe quoting)
            try:
                # Basic FTS5 escape: wrap in double quotes, escape double quotes by doubling them
                query_escaped = request.query.replace('"', '""')
                fts_query = f'"{query_escaped}"'
                fts_rows = canonical.connection.execute(
                    "SELECT h.reference FROM toxicology_herbs h "
                    "JOIN toxicology_fts f ON h.herb_id = f.herb_id "
                    "WHERE toxicology_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_query, result_limit * 2)
                ).fetchall()
                for row in fts_rows:
                    ref = str(row["reference"])
                    if ref not in exact_boosts and ref not in lexical_ids:
                        lexical_ids.append(ref)
            except Exception as fts_exc:
                logger.warning(
                    f"Toxicology FTS search failed for query '{request.query}': {fts_exc}"
                )

        except Exception as exc:
            logger.error(f"Toxicology SQLite search failed: {exc}")
            sqlite_failed = True

        # 2. Vector search (Qdrant)
        vector_ids: list[str] = []
        vector_failed = False
        if settings.vector_mode != "disabled":
            try:
                vector = get_vector_runtime()
                if vector.store is not None and vector.manifest is not None:
                    # Snapshot check
                    sq_row = canonical.connection.execute(
                        "SELECT source_snapshot FROM toxicology_snapshots"
                    ).fetchone()
                    sq_snapshot = sq_row[0] if sq_row else None
                    v_snapshot = vector.manifest.source_snapshot

                    if sq_snapshot and v_snapshot and sq_snapshot != v_snapshot:
                        logger.error(
                            f"Toxicology snapshot mismatch: SQLite {sq_snapshot[:8]} "
                            f"!= Qdrant {v_snapshot[:8]}. Vector search disabled."
                        )
                    else:
                        hits = vector.store.search(
                            settings.qdrant_collection_alias,
                            vector.embedding.embed_query(request.query),
                            scope,
                            result_limit * 2,
                        )
                        # Map chunk_ids to references
                        c_ids = [hit.chunk_id for hit in hits]
                        chunks = canonical.get_chunks(scope, c_ids)
                        for chunk in chunks:
                            payload = json.loads(chunk.text)
                            ref = payload.get("reference")
                            if ref:
                                vector_ids.append(ref)
            except Exception as exc:
                logger.error(f"Toxicology vector search failed: {exc}")
                vector_failed = True

        if not lexical_ids and not vector_ids:
            if sqlite_failed and (vector_failed or settings.vector_mode == "disabled"):
                raise RuntimeError("toxicology search failed: both SQLite and Qdrant unavailable")
            return SearchMedicalKnowledgeOutput(results=[])

        # 3. RRF
        fused = reciprocal_rank_fusion(
            lexical_ids, vector_ids, exact_boosts=exact_boosts
        )

        # 4. Resolve full records
        results: list[dict[str, Any]] = []
        top_refs = [item.identifier for item in fused[:result_limit]]
        if top_refs:
            marks = ",".join("?" for _ in top_refs)
            herb_rows = canonical.connection.execute(
                f"SELECT * FROM toxicology_herbs WHERE reference IN ({marks})",
                top_refs
            ).fetchall()

            herbs_by_ref = {}
            for row in herb_rows:
                raw_herb = dict(row)
                h_id = raw_herb["herb_id"]
                herb = {
                    field: _truncate_toxicology_value(raw_herb[field])
                    for field in TOXICOLOGY_HERB_FIELDS
                    if raw_herb.get(field) is not None
                }
                # Keep only LLM-relevant compound fields and cap nested records.
                c_rows = canonical.connection.execute(
                    "SELECT name, formula, cas "
                    "FROM toxicology_compounds WHERE herb_id = ? "
                    "ORDER BY compound_id LIMIT ?",
                    (h_id, TOXICOLOGY_COMPOUND_LIMIT),
                ).fetchall()
                herb["toxic_compounds"] = [
                    {
                        key: _truncate_toxicology_value(value)
                        for key, value in dict(compound).items()
                        if value is not None
                    }
                    for compound in c_rows
                ]
                herbs_by_ref[raw_herb["reference"]] = herb

            results = [herbs_by_ref[ref] for ref in top_refs if ref in herbs_by_ref]

        return SearchMedicalKnowledgeOutput(results=results)

    registry.register_tool(
        ToolDefinition[NormalizeHerbsInput, NormalizeHerbsOutput](
            name="normalize_herbs",
            version=TOOL_VERSION,
            description="标准化、去重中药材名称。",
            input_model=NormalizeHerbsInput,
            output_model=NormalizeHerbsOutput,
            required_permissions=frozenset({"herbs:normalize"}),
            handler=normalize,
        )
    )
    registry.register_tool(
        ToolDefinition[SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput](
            name="search_medical_knowledge",
            version=TOOL_VERSION,
            description="检索业务数据库中的医学知识，返回可引用的只读检索结果。",
            input_model=SearchMedicalKnowledgeInput,
            output_model=SearchMedicalKnowledgeOutput,
            required_permissions=frozenset({"knowledge:search"}),
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_retries=1),
            handler=search_medical_knowledge,
        )
    )
    registry.register_tool(
        ToolDefinition[SearchMedicalKnowledgeInput, SearchMedicalKnowledgeOutput](
            name="search_toxicology_knowledge",
            version=TOOL_VERSION,
            description=(
                "检索毒理索引中的中药毒理记录，返回 herb_basic:id、"
                "毒性字段、有毒成分及依据链接。"
            ),
            input_model=SearchMedicalKnowledgeInput,
            output_model=SearchMedicalKnowledgeOutput,
            required_permissions=frozenset({"knowledge:search"}),
            timeout_seconds=settings.toxicology_tool_timeout_seconds,
            retry_policy=RetryPolicy(max_retries=0),
            handler=search_toxicology_knowledge,
        )
    )
    return registry
