import os

import pytest

os.environ["AGENT_INTERNAL_TOKEN"] = "test-only-agent-token"
os.environ["AGENT_TESTING"] = "true"
os.environ.setdefault("AGENT_MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("AGENT_MYSQL_PORT", "33306")
os.environ.setdefault("AGENT_MYSQL_USER", "root")
os.environ.setdefault("AGENT_MYSQL_PASSWORD", "root123")
os.environ.setdefault("AGENT_MYSQL_DATABASE", "ai_medical_db")


@pytest.fixture(autouse=True)
def clean_agent_tables():
    from app.services.mysql import MySQLDatabase

    tables = (
        "agent_chat_events",
        "agent_chat_turns",
        "agent_tool_audits",
        "agent_workflow_runs",
        "knowledge_legacy_evidence_mappings",
        "knowledge_document_chunks",
        "knowledge_document_blocks",
        "knowledge_ingestion_jobs",
        "knowledge_document_versions",
        "knowledge_documents",
        "knowledge_embedding_cache",
        "knowledge_index_manifests",
        "knowledge_toxicology_compounds",
        "knowledge_toxicology_herbs",
        "knowledge_toxicology_snapshots",
    )
    database = MySQLDatabase()
    with database.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in tables:
            cursor.execute(f"TRUNCATE TABLE `{table}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
    yield
