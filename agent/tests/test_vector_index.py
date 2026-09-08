from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.models.knowledge import (
    DocumentChunk,
    IndexManifest,
    ManifestStatus,
    OwnershipScope,
    SourceLocator,
)
from app.services.embeddings import (
    DeterministicTestEmbedding,
    EmbeddingValidationError,
    LazySentenceTransformerEmbedding,
)
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.vector_index import IndexManager, ManifestMismatchError, QdrantVectorStore


def manifest(name: str, fingerprint: str, dimension: int = 8) -> IndexManifest:
    return IndexManifest(
        manifest_id=name,
        collection_name=name,
        alias="active",
        generation=name,
        schema_version=1,
        vector_name="dense",
        dimension=dimension,
        embedding_fingerprint=fingerprint,
        payload_schema_version=1,
        source_snapshot="snapshot",
    )


def item(scope: OwnershipScope, name: str) -> DocumentChunk:
    text = f"content {name}"
    return DocumentChunk(
        chunk_id=name,
        version_id=f"v-{name}",
        scope=scope,
        ordinal=0,
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        token_count=2,
        chunker_fingerprint="c",
        locator=SourceLocator(source_uri=f"doc-{name}"),
    )


def test_embedding_is_lazy_validated_deterministic_and_cached(tmp_path: Path) -> None:
    test = DeterministicTestEmbedding(8)
    assert test.embed_query("same") == test.embed_query("same")
    assert test.embed_query("same") != test.embed_query("different")
    loaded = 0

    class Fake:
        max_seq_length = 0

        def get_sentence_embedding_dimension(self) -> int:
            return 8

        def encode(self, texts: list[str], **_: object) -> list[list[float]]:
            return [[1.0] * 8 for _ in texts]

    def loader() -> Fake:
        nonlocal loaded
        loaded += 1
        return Fake()

    real = LazySentenceTransformerEmbedding(
        "configured", "rev", 8, max_seq_length=512, loader=loader
    )
    assert loaded == 0 and real.health()["loaded"] is False
    assert len(real.embed_query("query")) == 8 and loaded == 1
    assert real._instance is not None
    assert real._instance.max_seq_length == 512
    repo = SQLiteCanonicalRepository(tmp_path / "cache.db")
    vector = test.embed_query("cache")
    digest = hashlib.sha256(b"cache").hexdigest()
    repo.cache_embedding(digest, test.fingerprint, vector)
    assert repo.get_cached_embedding(digest, test.fingerprint) == vector


def test_qdrant_idempotency_filters_manifest_rebuild_rollback_reconcile() -> None:
    store = QdrantVectorStore.memory()
    embedding = DeterministicTestEmbedding(8)
    scope = OwnershipScope(tenant_id="t", project_id="p")
    other = OwnershipScope(tenant_id="t", project_id="other")
    chunks = [item(scope, "a"), item(scope, "orphan"), item(other, "hidden")]
    vectors = embedding.embed_documents([chunk.text for chunk in chunks])
    first = manifest("generation-1", embedding.fingerprint)
    store.upsert(first, chunks, vectors)
    store.upsert(first, chunks, vectors)
    assert store.count(first.collection_name) == 3
    assert {hit.chunk_id for hit in store.search(first.collection_name, vectors[0], scope, 10)} == {
        "a",
        "orphan",
    }
    with pytest.raises(ManifestMismatchError):
        store.ensure_collection(first.model_copy(update={"dimension": 9}))
    store.activate("active", first.collection_name)
    assert store.reconcile("active", scope, {"a"}) == {"eligible": 1, "orphaned": 1, "remaining": 1}
    second = manifest("generation-2", embedding.fingerprint)
    active = IndexManager(store).rebuild(second, [chunks[0]], [vectors[0]], smoke_vector=vectors[0])
    assert active.status is ManifestStatus.ACTIVE
    assert store.alias_targets["active"] == "generation-2"
    assert store.rollback("active") == "generation-1"
    assert store.delete("active", scope, chunk_id="a") == 1
    assert store.count("generation-1", other) == 1


def test_failed_rebuild_never_activates() -> None:
    store = QdrantVectorStore.memory()
    embedding = DeterministicTestEmbedding(8)
    scope = OwnershipScope(tenant_id="t", project_id="p")
    chunk = item(scope, "a")
    store.activate("active", manifest("old", embedding.fingerprint).collection_name)
    with pytest.raises((ValueError, EmbeddingValidationError)):
        IndexManager(store).rebuild(manifest("bad", embedding.fingerprint), [chunk], [[1.0]])
    assert store.alias_targets["active"] == "old"
