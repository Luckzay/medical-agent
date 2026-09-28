from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from uuid import uuid4

from elasticsearch import Elasticsearch
from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.models.knowledge import IndexManifest
from app.services.knowledge.storage.embedding import (
    DeterministicTestEmbedding,
    LazySentenceTransformerEmbedding,
)
from app.services.knowledge.storage.lexical import ElasticsearchLexicalStore, LexicalStore
from app.services.knowledge.storage.mysql_repository import MySQLCanonicalRepository
from app.services.knowledge.storage.vector import QdrantVectorStore


@dataclass(frozen=True)
class VectorRuntime:
    embedding: DeterministicTestEmbedding | LazySentenceTransformerEmbedding
    store: QdrantVectorStore | None
    manifest: IndexManifest | None


def build_elasticsearch_client(settings: Settings) -> Elasticsearch:
    basic_auth = None
    if settings.elasticsearch_username:
        basic_auth = (
            settings.elasticsearch_username,
            settings.elasticsearch_password.get_secret_value()
            if settings.elasticsearch_password
            else "",
        )
    options: dict[str, object] = {
        "basic_auth": basic_auth,
        "request_timeout": settings.elasticsearch_timeout_seconds,
        "verify_certs": settings.elasticsearch_verify_certs,
    }
    if settings.elasticsearch_ca_certs:
        options["ca_certs"] = settings.elasticsearch_ca_certs
    return Elasticsearch(settings.elasticsearch_url, **options)  # type: ignore[arg-type]


def build_lexical_store(
    settings: Settings | None = None,
    repository: MySQLCanonicalRepository | None = None,
) -> LexicalStore:
    del repository
    settings = settings or get_settings()
    return ElasticsearchLexicalStore(
        build_elasticsearch_client(settings),
        settings.elasticsearch_index_alias,
        timeout_seconds=settings.elasticsearch_timeout_seconds,
    )


def build_vector_runtime(settings: Settings | None = None) -> VectorRuntime:
    settings = settings or get_settings()
    repository = MySQLCanonicalRepository()
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
        collection_name=f"toxicology_v{generation}",
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


@lru_cache(maxsize=1)
def get_vector_runtime() -> VectorRuntime:
    return build_vector_runtime(get_settings())
