from __future__ import annotations

import json
from pathlib import Path

from app.models.knowledge import OwnershipScope
from app.scripts.migrate_literature import migrate
from app.scripts.shadow_retrieval import compare
from app.services.knowledge_observability import KnowledgeMetrics


def test_real_migration_is_repeatable_and_all_legacy_ids_resolve(tmp_path: Path) -> None:
    source = (
        Path(__file__).parents[1]
        / "resources/literature/TCM_Supramolecular_Literature_Search_EN_v3_filled.xlsx"
    )
    database = tmp_path / "canonical.db"
    scope = OwnershipScope(tenant_id="default", project_id="literature")
    first = migrate(source, database, scope)
    second = migrate(source, database, scope)
    assert (
        first["blocks"]
        == first["chunks"]
        == first["legacy_mappings"]
        == first["resolved_mappings"]
        == 131
    )
    assert first["created_version"] is True and second["created_version"] is False
    assert (
        first["document_id"] == second["document_id"]
        and first["version_id"] == second["version_id"]
    )


def test_shadow_does_not_change_agent_results_and_metrics_are_safe(
    tmp_path: Path, caplog: object
) -> None:
    source = (
        Path(__file__).parents[1]
        / "resources/literature/TCM_Supramolecular_Literature_Search_EN_v3_filled.xlsx"
    )
    results = compare(source, tmp_path / "evidence.db", ["licorice assembly"])
    assert results[0]["agent_visible_ids"] == results[0]["lexical_ids"]
    assert results[0]["agent_results_changed"] is False
    metrics = KnowledgeMetrics()
    with metrics.stage("embedding", tenant_id="safe-tenant"):
        metrics.increment("embedding_calls")
    rendered = json.dumps(metrics.snapshot())
    assert "credential" not in rendered and metrics.counters["embedding_calls"] == 1
