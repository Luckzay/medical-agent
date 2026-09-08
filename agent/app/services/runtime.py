from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.models.knowledge import IndexManifest
from app.services.embeddings import DeterministicTestEmbedding, LazySentenceTransformerEmbedding
from app.services.knowledge_repository import SQLiteCanonicalRepository
from app.services.vector_index import QdrantVectorStore


@dataclass(frozen=True)
class VectorRuntime:
    embedding: DeterministicTestEmbedding | LazySentenceTransformerEmbedding
    store: QdrantVectorStore | None
    manifest: IndexManifest | None


def build_runtime(settings: Settings | None = None) -> VectorRuntime:
    settings = settings or get_settings()
    repository = SQLiteCanonicalRepository(settings.canonical_database_path)
    if settings.vector_mode == "disabled":
        return VectorRuntime(DeterministicTestEmbedding(settings.embedding_dimension), None, None)
    if settings.embedding_provider != "sentence_transformers":
        raise ValueError("real vector modes require sentence_transformers")
    embedding = LazySentenceTransformerEmbedding(
        settings.embedding_model,
        settings.embedding_revision,
        settings.embedding_dimension,
        normalize=settings.embedding_normalize,
        batch_size=settings.embedding_batch_size,
        retries=settings.embedding_retries,
        timeout_seconds=settings.embedding_timeout_seconds,
        device=settings.embedding_device,
        max_seq_length=settings.embedding_max_seq_length,
    )
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=max(1, int(settings.qdrant_timeout_seconds)),
    )
    store = QdrantVectorStore(client, repository)
    active = store.active_manifest(settings.qdrant_collection_alias)
    if active is not None:
        return VectorRuntime(embedding, store, active)
    generation = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    manifest = IndexManifest(
        manifest_id=str(uuid4()),
        collection_name=f"medical_evidence_v{generation}",
        alias=settings.qdrant_collection_alias,
        generation=generation,
        schema_version=1,
        vector_name="dense",
        dimension=settings.embedding_dimension,
        normalized=settings.embedding_normalize,
        embedding_fingerprint=embedding.fingerprint,
        payload_schema_version=1,
        source_snapshot="pending",
    )
    return VectorRuntime(embedding, store, manifest)
