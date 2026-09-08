from __future__ import annotations

import hashlib
from pathlib import Path

from app.models.knowledge import (
    CanonicalDocument,
    DocumentChunk,
    DocumentVersion,
    IndexManifest,
    OwnershipScope,
    SourceLocator,
)
from app.services.embeddings import DeterministicTestEmbedding
from app.services.hybrid_retrieval import HybridRetriever, reciprocal_rank_fusion
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.vector_index import QdrantVectorStore


def add_chunk(
    repo: SQLiteCanonicalRepository,
    scope: OwnershipScope,
    name: str,
    text: str,
    *,
    active: bool = True,
) -> DocumentChunk:
    digest = hashlib.sha256(text.encode()).hexdigest()
    document = CanonicalDocument(
        document_id=f"doc-{name}",
        scope=scope,
        logical_source=f"memory:{name}",
        media_type="text/plain",
    )
    version = DocumentVersion(
        version_id=f"version-{name}",
        document_id=document.document_id,
        scope=scope,
        source_hash=digest,
        source_locator=SourceLocator(source_uri=f"memory:{name}"),
        media_type="text/plain",
        parser_fingerprint="p",
    )
    repo.create_version(document, version)
    chunk = DocumentChunk(
        chunk_id=f"chunk-{name}",
        version_id=version.version_id,
        scope=scope,
        ordinal=0,
        text=text,
        content_hash=digest,
        token_count=len(text.split()),
        chunker_fingerprint="c",
        locator=version.source_locator,
    )
    repo.put_chunks(scope, [chunk])
    if active:
        repo.activate_version(scope, document.document_id, version.version_id)
    return chunk


def test_rrf_is_stable_and_exact_identifiers_win() -> None:
    first = reciprocal_rank_fusion(["b", "a"], ["a", "b"], exact_boosts={"b": ("smiles",)})
    assert [item.identifier for item in first] == ["b", "a"]
    assert first == reciprocal_rank_fusion(["b", "a"], ["a", "b"], exact_boosts={"b": ("smiles",)})


def test_hybrid_semantic_scope_broken_lineage_and_degradation(tmp_path: Path) -> None:
    repo = SQLiteCanonicalRepository(tmp_path / "hybrid.db")
    scope = OwnershipScope(tenant_id="t", project_id="p")
    other = OwnershipScope(tenant_id="t", project_id="other")
    semantic = add_chunk(repo, scope, "semantic", "multilingual botanical assembly")
    hidden = add_chunk(repo, other, "hidden", "multilingual botanical assembly")
    tombstoned = add_chunk(repo, scope, "old", "obsolete", active=False)
    embedding = DeterministicTestEmbedding(8)
    manifest = IndexManifest(
        manifest_id="m",
        collection_name="vectors",
        alias="active",
        generation="g",
        schema_version=1,
        vector_name="dense",
        dimension=8,
        embedding_fingerprint=embedding.fingerprint,
        payload_schema_version=1,
        source_snapshot="s",
    )
    store = QdrantVectorStore.memory()
    chunks = [semantic, hidden, tombstoned]
    store.upsert(manifest, chunks, embedding.embed_documents([chunk.text for chunk in chunks]))
    store.activate("active", "vectors")
    result = HybridRetriever(repo, embedding, store, "active").search(
        "multilingual botanical assembly", scope, ["broken"], limit=10
    )
    assert semantic.chunk_id in {chunk.chunk_id for chunk in result.chunks}
    assert hidden.chunk_id not in {chunk.chunk_id for chunk in result.chunks}
    assert tombstoned.chunk_id not in {chunk.chunk_id for chunk in result.chunks}
    assert result.broken_lineage >= 1
    degraded = HybridRetriever(repo, embedding, None, "active").search(
        "query", scope, [semantic.chunk_id]
    )
    assert degraded.degraded and degraded.diagnostics[0].degraded_reason == "vector_disabled"
