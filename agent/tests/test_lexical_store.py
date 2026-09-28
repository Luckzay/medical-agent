from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.knowledge import OwnershipScope
from app.scripts.build_toxicology_index import build_elasticsearch_index, elasticsearch_documents
from app.services.knowledge.storage.lexical import ElasticsearchLexicalStore, LexicalStoreError


@pytest.fixture
def records() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "herb_name": "附子",
            "reference": "herb_basic:1",
            "virulence": "有毒",
            "toxicity_mechanism": "乌头碱影响钠通道",
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


def test_elasticsearch_mapping_dsl_bulk_and_atomic_alias(records) -> None:
    client = MagicMock()
    client.options.return_value = client
    client.bulk.return_value = {"items": [{"index": {"_id": "herb_basic:1", "status": 201}}]}
    client.indices.get_alias.return_value = {"old-index": {"aliases": {"tox": {}}}}
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "herb_basic:1",
                    "_score": 12.5,
                    "_source": {
                        "reference": "herb_basic:1",
                        "source_snapshot": "snapshot-1",
                        "name": "附子",
                        "compound_names": ["乌头碱"],
                        "cas_numbers": ["302-27-2"],
                        "formulas": ["C34H47NO11"],
                    },
                }
            ]
        }
    }
    store = ElasticsearchLexicalStore(client, "tox", timeout_seconds=2)
    mapping = store.mapping()
    assert mapping["dynamic"] == "strict"
    assert mapping["properties"]["name"]["fields"]["exact"]["type"] == "keyword"

    scope = OwnershipScope(tenant_id="default", project_id="toxicology")
    documents = elasticsearch_documents(records, scope, "snapshot-1")
    assert store.bulk_index("tox_v1", documents) == 1
    assert client.bulk.call_args.kwargs["operations"][0]["index"]["_id"] == "herb_basic:1"

    result = store.search("302-27-2", scope, 5, {"source_snapshot": "snapshot-1"})
    query = client.search.call_args.kwargs["query"]
    assert {"term": {"tenant_id": "default"}} in query["bool"]["filter"]
    assert result.candidates[0].exact_fields == ("cas_numbers",)

    store.activate("tox_v1")
    assert client.indices.update_aliases.call_args.kwargs["actions"] == [
        {"remove": {"index": "old-index", "alias": "tox"}},
        {"add": {"index": "tox_v1", "alias": "tox"}},
    ]


def test_elasticsearch_bulk_checks_each_item() -> None:
    client = MagicMock()
    client.options.return_value = client
    client.bulk.return_value = {
        "items": [
            {"index": {"status": 201}},
            {"index": {"status": 400, "error": {"type": "mapper_parsing_exception"}}},
        ]
    }
    store = ElasticsearchLexicalStore(client, "tox")
    with pytest.raises(LexicalStoreError, match="herb_basic:2"):
        store.bulk_index(
            "tox_v1", [{"reference": "herb_basic:1"}, {"reference": "herb_basic:2"}]
        )


def test_build_elasticsearch_index_reconciles_ids(records) -> None:
    store = MagicMock(spec=ElasticsearchLexicalStore)
    store.versioned_index.return_value = "tox_v1_snapshot"
    store.bulk_index.return_value = 1
    store.count.return_value = 1
    store.document_ids.return_value = {"herb_basic:1"}
    scope = OwnershipScope(tenant_id="default", project_id="toxicology")
    assert build_elasticsearch_index(store, records, scope, "snapshot-1", "1") == "tox_v1_snapshot"
    store.activate.assert_called_once_with("tox_v1_snapshot")


def test_build_cli_dry_run_defaults_to_elasticsearch(records, capsys) -> None:
    settings = MagicMock(vector_mode="disabled", evidence_project_id="toxicology")
    settings.evidence_tenant_id = "default"
    with (
        patch("app.scripts.build_toxicology_index.get_settings", return_value=settings),
        patch("app.scripts.build_toxicology_index.load_records", return_value=(records, "db")),
        patch("app.scripts.build_toxicology_index.build_vector_runtime") as build_runtime,
        patch("sys.argv", ["build_toxicology_index", "--dry-run"]),
    ):
        from app.scripts.build_toxicology_index import main

        main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["targets"] == ["elasticsearch"]
    build_runtime.assert_not_called()


def test_runtime_always_selects_elasticsearch() -> None:
    from app.core.config import Settings
    from app.services.knowledge.storage.factory import build_lexical_store

    settings = Settings(internal_token="x" * 16)
    with patch(
        "app.services.knowledge.storage.factory.build_elasticsearch_client",
        return_value=MagicMock(),
    ):
        selected = build_lexical_store(settings)
    assert isinstance(selected, ElasticsearchLexicalStore)
    assert selected.backend == "elasticsearch"


def test_build_cli_requires_vector_mode_only_for_explicit_qdrant() -> None:
    settings = MagicMock(vector_mode="disabled", evidence_project_id="toxicology")
    with (
        patch("app.scripts.build_toxicology_index.get_settings", return_value=settings),
        patch("sys.argv", ["build_toxicology_index", "--targets", "qdrant", "--dry-run"]),
        pytest.raises(SystemExit, match="AGENT_VECTOR_MODE"),
    ):
        from app.scripts.build_toxicology_index import main

        main()


def test_elasticsearch_credentials_distinguish_none_and_empty_strings(monkeypatch) -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    base = {"internal_token": "x" * 16}
    assert Settings(**base).elasticsearch_username is None
    monkeypatch.setenv("AGENT_ELASTICSEARCH_USERNAME", "")
    monkeypatch.setenv("AGENT_ELASTICSEARCH_PASSWORD", "")
    assert Settings(**base).elasticsearch_username is None
    with pytest.raises(ValidationError, match="cannot be empty strings"):
        Settings(**base, elasticsearch_username="", elasticsearch_password="")
    with pytest.raises(ValidationError, match="configured together"):
        Settings(**base, elasticsearch_username="elastic", elasticsearch_password=None)
