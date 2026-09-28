from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.knowledge import OwnershipScope
from app.models.tooling import SearchMedicalKnowledgeInput
from app.scripts.build_toxicology_index import load_db_environment, sync_structured_mysql
from app.services.knowledge.retrieval.toxicology import search_toxicology
from app.services.knowledge.storage.embedding import DeterministicTestEmbedding
from app.services.knowledge.storage.factory import VectorRuntime
from app.services.knowledge.storage.lexical import LexicalSearchResult, RetrievalCandidate
from app.services.knowledge.storage.mysql_repository import MySQLCanonicalRepository


def records() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "herb_name": "附子",
            "reference": "herb_basic:1",
            "virulence": "有毒",
            "toxicity_mechanism": "乌头碱影响钠通道",
            "pathological_examination": "心肌损伤",
            "crowd_taboo": "孕妇慎用",
            "symptom_contraindications": "心律失常",
            "adr": "恶心",
            "typical_cases_of_adr": "病例",
            "clinical_suggestion": "遵医嘱",
            "clinical_suggestion_basis": "指南",
            "link_to_clinical_suggestion": "https://example.test/guideline",
            "toxic_compounds": [
                {
                    "compound_id": 11,
                    "compound_name": "乌头碱",
                    "formula": "C34H47NO11",
                    "cas": "302-27-2",
                }
            ],
        }
    ]


def test_mysql_toxicology_snapshot_is_replaced_atomically() -> None:
    repository = MySQLCanonicalRepository()
    sync_structured_mysql(repository, records(), "medical", "snapshot-1")
    assert repository.toxicology_counts() == (1, 0)
    row = repository.toxicology_records(["herb_basic:1"])[0]
    assert row["name"] == "附子"
    assert row["toxic_compounds"][0]["cas"] == "302-27-2"


def test_search_uses_elasticsearch_identifiers_and_mysql_payload() -> None:
    repository = MySQLCanonicalRepository()
    sync_structured_mysql(repository, records(), "medical", "snapshot-1")
    lexical = MagicMock()
    lexical.search.return_value = LexicalSearchResult(
        [RetrievalCandidate("herb_basic:1", 5.0, ("name",), "elasticsearch")],
        "elasticsearch",
        "snapshot-1",
    )
    settings = MagicMock()
    settings.evidence_tenant_id = "default"
    settings.evidence_project_id = "toxicology"
    settings.vector_mode = "disabled"
    settings.qdrant_collection_alias = "toxicology_active"
    settings.fusion_rrf_k = 60
    settings.fusion_policy_version = "rrf-v1"
    settings.lexical_candidate_limit = 10
    settings.vector_candidate_limit = 10
    vector = VectorRuntime(DeterministicTestEmbedding(8), None, None)
    with patch(
        "app.services.knowledge.retrieval.toxicology.build_lexical_store",
        return_value=lexical,
    ):
        output = search_toxicology(
            SearchMedicalKnowledgeInput(query="附子"),
            settings,
            repository=repository,
            vector_runtime=vector,
        )
    assert output.results[0]["name"] == "附子"
    assert output.results[0]["toxic_compounds"][0]["name"] == "乌头碱"


def test_load_db_environment_does_not_override_process_environment(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_HOST=file-host\nDB_NAME=file-name\n", encoding="utf-8")
    monkeypatch.setenv("DB_HOST", "process-host")
    monkeypatch.delenv("DB_NAME", raising=False)
    load_db_environment(env)
    assert __import__("os").environ["DB_HOST"] == "process-host"
    assert __import__("os").environ["DB_NAME"] == "file-name"


def test_scope_is_forwarded_to_elasticsearch() -> None:
    scope = OwnershipScope(tenant_id="tenant", project_id="toxicology")
    assert scope.tenant_id == "tenant"
