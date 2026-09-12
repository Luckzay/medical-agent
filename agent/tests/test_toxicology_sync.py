import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.knowledge import DocumentChunk, OwnershipScope, SourceLocator
from app.models.tooling import SearchMedicalKnowledgeInput
from app.scripts.build_toxicology_index import sync_structured_sqlite
from app.services.builtin_tools import build_tool_registry
from app.services.knowledge_repository import SQLiteCanonicalRepository


@pytest.fixture
def temp_repo(tmp_path):
    db_path = tmp_path / "test_canonical.db"
    return SQLiteCanonicalRepository(db_path)


def test_toxicology_schema_and_sync(temp_repo):
    records = [
        {
            "id": 1,
            "herb_name": "Test Herb",
            "reference": "herb_basic:1",
            "virulence": "High",
            "toxic_compounds": [
                {
                    "compound_id": 101,
                    "compound_name": "Toxin A",
                    "formula": "C10H20",
                    "cas": "123-45-6"
                }
            ]
        }
    ]
    sync_structured_sqlite(temp_repo, records, "test_db", "test_snapshot")

    # Check herb
    herb = temp_repo.connection.execute(
        "SELECT * FROM toxicology_herbs WHERE herb_id = 1"
    ).fetchone()
    assert herb["name"] == "Test Herb"
    assert herb["virulence"] == "High"
    assert herb["logical_source"] == "mysql://test_db/herb_basic/1"

    # Check compound
    compound = temp_repo.connection.execute(
        "SELECT * FROM toxicology_compounds WHERE herb_id = 1"
    ).fetchone()
    assert compound["compound_id"] == 101
    assert compound["name"] == "Toxin A"
    assert compound["formula"] == "C10H20"
    assert compound["cas"] == "123-45-6"
    assert compound["logical_source"] == "mysql://test_db/herb_toxiccompound/101"

    # Check FTS
    fts = temp_repo.connection.execute(
        "SELECT * FROM toxicology_fts WHERE name = 'Test Herb'"
    ).fetchone()
    assert fts is not None
    assert "Toxin A" in fts["compound_names"]
    assert "123-45-6" in fts["cas_numbers"]

    # Check snapshot
    snapshot = temp_repo.connection.execute(
        "SELECT source_snapshot FROM toxicology_snapshots"
    ).fetchone()
    assert snapshot[0] == "test_snapshot"


def test_search_toxicology_hybrid_logic(temp_repo):
    # Setup data
    records = [
        {
            "id": 1,
            "herb_name": "Aconite",
            "reference": "herb_basic:1",
            "virulence": "Extreme",
            "toxic_compounds": [
                {
                    "compound_id": 101,
                    "compound_name": "Aconitine",
                    "cas": "302-27-2",
                    "formula": "C34H47NO11"
                }
            ]
        },
        {
            "id": 2,
            "herb_name": "Ginseng",
            "reference": "herb_basic:2",
            "virulence": "Low",
            "toxic_compounds": []
        }
    ]
    sync_structured_sqlite(temp_repo, records, "test_db", "snap1")

    # Mock settings and runtime
    with patch("app.services.builtin_tools.get_settings") as mock_settings, \
         patch("app.services.builtin_tools.build_runtime") as mock_runtime:

        mock_settings.return_value.canonical_database_path = temp_repo.path
        mock_settings.return_value.vector_mode = "required"
        mock_settings.return_value.qdrant_collection_alias = "tox_active"
        mock_settings.return_value.evidence_tenant_id = "t1"
        mock_settings.return_value.evidence_project_id = "toxicology"
        mock_settings.return_value.knowledge_api_url = "http://localhost/api"
        mock_settings.return_value.internal_token = "token"
        mock_settings.return_value.knowledge_timeout_seconds = 10

        analysis = MagicMock()
        registry = build_tool_registry(analysis)
        search_tool = registry.get_tool("search_toxicology_knowledge")

        # 1. Test Exact Match (CAS)
        mock_settings.return_value.vector_mode = "disabled"
        request = SearchMedicalKnowledgeInput(query="302-27-2", limit=10)
        output = search_tool.handler(request)
        assert len(output.results) == 1
        assert output.results[0]["name"] == "Aconite"
        assert output.results[0]["toxic_compounds"][0]["cas"] == "302-27-2"

        # 2. Test FTS Match with Special Chars (should not crash)
        request = SearchMedicalKnowledgeInput(query="302-27-2", limit=10)
        output = search_tool.handler(request)
        assert len(output.results) >= 1

        # 3. Test Hybrid RRF + Snapshot Check
        mock_settings.return_value.vector_mode = "required"
        mock_vector = MagicMock()
        mock_runtime.return_value = mock_vector
        mock_vector.manifest.source_snapshot = "snap1"
        mock_vector.store.search.return_value = [
            MagicMock(chunk_id="chunk2", score=0.9)
        ]

        with patch.object(SQLiteCanonicalRepository, "get_chunks") as mock_get_chunks:
            mock_get_chunks.return_value = [
                DocumentChunk(
                    chunk_id="chunk2",
                    version_id="v1",
                    scope=OwnershipScope(tenant_id="t1", project_id="toxicology"),
                    ordinal=0,
                    content_hash="a" * 64,
                    text=json.dumps({"reference": "herb_basic:2"}),
                    token_count=10,
                    chunker_fingerprint="f1",
                    locator=SourceLocator(source_uri="mysql://test/2")
                )
            ]

            request = SearchMedicalKnowledgeInput(query="Aconite", limit=10)
            output = search_tool.handler(request)

            names = [r["name"] for r in output.results]
            assert "Aconite" in names
            assert "Ginseng" in names

            # 4. Test Snapshot Mismatch (Vector Degradation)
            mock_vector.manifest.source_snapshot = "mismatch_snap"
            request = SearchMedicalKnowledgeInput(query="Aconite", limit=10)
            output = search_tool.handler(request)

            names = [r["name"] for r in output.results]
            assert "Aconite" in names
            assert "Ginseng" not in names


def test_search_toxicology_failure_handling(temp_repo):
    with patch("app.services.builtin_tools.get_settings") as mock_settings, \
         patch("app.services.builtin_tools.build_runtime") as mock_runtime, \
         patch("app.services.builtin_tools.SQLiteCanonicalRepository") as mock_repo_class:

        mock_settings.return_value.canonical_database_path = temp_repo.path
        mock_settings.return_value.vector_mode = "required"
        mock_settings.return_value.evidence_tenant_id = "t1"
        mock_settings.return_value.evidence_project_id = "toxicology"
        mock_settings.return_value.knowledge_api_url = "http://localhost/api"
        mock_settings.return_value.internal_token = "token"
        mock_settings.return_value.knowledge_timeout_seconds = 10

        analysis = MagicMock()
        registry = build_tool_registry(analysis)
        search_tool = registry.get_tool("search_toxicology_knowledge")

        # Mock SQLite failure
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.connection.execute.side_effect = Exception("SQLite error")

        # Mock Vector failure
        mock_runtime.side_effect = Exception("Qdrant down")

        request = SearchMedicalKnowledgeInput(query="test", limit=10)
        with pytest.raises(RuntimeError, match="toxicology search failed"):
            search_tool.handler(request)
