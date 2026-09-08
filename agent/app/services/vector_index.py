from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.models.knowledge import DocumentChunk, IndexManifest, ManifestStatus, OwnershipScope
from app.services.knowledge_repository import SQLiteCanonicalRepository


class ManifestMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class QdrantCandidate:
    chunk_id: str
    score: float
    point_id: str
    payload: dict[str, Any]


def assert_manifest_compatible(expected: IndexManifest, actual: IndexManifest) -> None:
    fields = (
        "dimension",
        "distance",
        "normalized",
        "embedding_fingerprint",
        "payload_schema_version",
        "vector_name",
    )
    mismatches = [field for field in fields if getattr(expected, field) != getattr(actual, field)]
    if mismatches:
        raise ManifestMismatchError(f"incompatible manifest fields: {', '.join(mismatches)}")


class QdrantVectorStore:
    def __init__(
        self, client: QdrantClient, repository: SQLiteCanonicalRepository | None = None
    ) -> None:
        self.client = client
        self.repository = repository
        self.manifests: dict[str, IndexManifest] = {
            item.collection_name: item
            for item in (repository.list_manifests() if repository else [])
        }
        self.alias_targets: dict[str, str] = {}
        self.alias_history: dict[str, list[str]] = {}
        try:
            for alias in self.client.get_aliases().aliases:
                self.alias_targets[alias.alias_name] = alias.collection_name
        except (AttributeError, NotImplementedError):
            pass

    def active_manifest(self, alias: str) -> IndexManifest | None:
        collection = self.alias_targets.get(alias)
        return self.manifests.get(collection) if collection else None

    @classmethod
    def memory(cls) -> QdrantVectorStore:
        return cls(QdrantClient(":memory:"))

    def ensure_collection(self, manifest: IndexManifest) -> None:
        known = self.manifests.get(manifest.collection_name)
        if known is not None:
            assert_manifest_compatible(manifest, known)
            return
        self.client.create_collection(
            collection_name=manifest.collection_name,
            vectors_config={
                manifest.vector_name: models.VectorParams(
                    size=manifest.dimension, distance=models.Distance.COSINE
                )
            },
        )
        for field in (
            "tenant_id",
            "project_id",
            "document_id",
            "version_id",
            "chunk_id",
            "status",
            "generation",
        ):
            self.client.create_payload_index(
                collection_name=manifest.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
        self.manifests[manifest.collection_name] = manifest
        if self.repository:
            self.repository.save_manifest(manifest)

    @staticmethod
    def point_id(chunk: DocumentChunk, manifest: IndexManifest) -> str:
        seed = "|".join(
            (
                chunk.scope.tenant_id,
                chunk.scope.project_id,
                chunk.version_id,
                chunk.chunk_id,
                manifest.vector_name,
                manifest.embedding_fingerprint,
            )
        )
        return str(uuid5(NAMESPACE_URL, seed))

    def upsert(
        self, manifest: IndexManifest, chunks: list[DocumentChunk], vectors: list[list[float]]
    ) -> int:
        self.ensure_collection(manifest)
        assert_manifest_compatible(manifest, self.manifests[manifest.collection_name])
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        points: list[models.PointStruct] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != manifest.dimension:
                raise ValueError("vector dimension mismatch")
            payload = {
                "tenant_id": chunk.scope.tenant_id,
                "project_id": chunk.scope.project_id,
                "document_id": chunk.locator.source_uri,
                "version_id": chunk.version_id,
                "chunk_id": chunk.chunk_id,
                "status": "ready",
                "generation": manifest.generation,
                "content_hash": chunk.content_hash,
            }
            points.append(
                models.PointStruct(
                    id=self.point_id(chunk, manifest),
                    vector={manifest.vector_name: vector},
                    payload=payload,
                )
            )
        if points:
            self.client.upsert(manifest.collection_name, points=points, wait=True)
        return len(points)

    def search(
        self,
        alias: str,
        vector: list[float],
        scope: OwnershipScope,
        limit: int,
        filters: dict[str, object] | None = None,
    ) -> list[QdrantCandidate]:
        collection = self.alias_targets.get(alias, alias)
        manifest = self.manifests[collection]
        must = [
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=scope.tenant_id)),
            models.FieldCondition(
                key="project_id", match=models.MatchValue(value=scope.project_id)
            ),
            models.FieldCondition(key="status", match=models.MatchValue(value="ready")),
        ]
        for key, value in (filters or {}).items():
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        response = self.client.query_points(
            collection_name=collection,
            query=vector,
            using=manifest.vector_name,
            query_filter=models.Filter(must=must),
            limit=limit,
            with_payload=True,
        )
        return [
            QdrantCandidate(
                chunk_id=str((point.payload or {})["chunk_id"]),
                score=float(point.score),
                point_id=str(point.id),
                payload=dict(point.payload or {}),
            )
            for point in response.points
        ]

    def delete(self, alias: str, scope: OwnershipScope, **selectors: str) -> int:
        collection = self.alias_targets.get(alias, alias)
        before = self.count(collection, scope)
        must = [
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=scope.tenant_id)),
            models.FieldCondition(
                key="project_id", match=models.MatchValue(value=scope.project_id)
            ),
        ]
        must.extend(
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in selectors.items()
        )
        self.client.delete(
            collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=must)),
            wait=True,
        )
        return before - self.count(collection, scope)

    def count(self, collection: str, scope: OwnershipScope | None = None) -> int:
        query_filter = None
        if scope is not None:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=scope.tenant_id)
                    ),
                    models.FieldCondition(
                        key="project_id", match=models.MatchValue(value=scope.project_id)
                    ),
                ]
            )
        return int(
            self.client.count(
                collection_name=collection, count_filter=query_filter, exact=True
            ).count
        )

    def activate(self, alias: str, collection: str) -> None:
        previous = self.alias_targets.get(alias)
        operations: list[models.AliasOperations] = []
        if previous:
            self.alias_history.setdefault(alias, []).append(previous)
            operations.append(
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
            )
        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)
            )
        )
        try:
            self.client.update_collection_aliases(change_aliases_operations=operations)
        except (NotImplementedError, ValueError):
            # QdrantLocal versions without alias support still exercise lifecycle via mapping.
            pass
        self.alias_targets[alias] = collection

    def retire(self, alias: str, retain: int = 2) -> list[str]:
        protected = {self.alias_targets.get(alias), *self.alias_history.get(alias, [])[-retain:]}
        retired: list[str] = []
        for collection in list(self.manifests):
            if collection not in protected:
                self.client.delete_collection(collection)
                self.manifests.pop(collection, None)
                retired.append(collection)
        return sorted(retired)

    def rollback(self, alias: str) -> str:
        history = self.alias_history.get(alias, [])
        if not history:
            raise ValueError("no healthy generation available for rollback")
        target = history.pop()
        current = self.alias_targets.get(alias)
        self.alias_targets[alias] = target
        if current:
            self.alias_history.setdefault(alias, []).append(current)
        return target

    def reconcile(
        self, alias: str, scope: OwnershipScope, eligible_chunk_ids: set[str]
    ) -> dict[str, int]:
        collection = self.alias_targets.get(alias, alias)
        points, _ = self.client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=scope.tenant_id)
                    ),
                    models.FieldCondition(
                        key="project_id", match=models.MatchValue(value=scope.project_id)
                    ),
                ]
            ),
            limit=10000,
            with_payload=True,
        )
        orphan_ids = [
            point.id
            for point in points
            if str((point.payload or {}).get("chunk_id")) not in eligible_chunk_ids
        ]
        if orphan_ids:
            self.client.delete(collection, points_selector=orphan_ids, wait=True)
        return {
            "eligible": len(eligible_chunk_ids),
            "orphaned": len(orphan_ids),
            "remaining": self.count(collection, scope),
        }

    def health(self) -> dict[str, object]:
        try:
            return {
                "available": True,
                "collections": len(self.client.get_collections().collections),
                "aliases": dict(self.alias_targets),
            }
        except Exception as exc:
            return {"available": False, "reason": type(exc).__name__}


class IndexManager:
    def __init__(self, store: QdrantVectorStore) -> None:
        self.store = store

    def rebuild(
        self,
        manifest: IndexManifest,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        *,
        smoke_vector: list[float] | None = None,
    ) -> IndexManifest:
        self.store.ensure_collection(manifest)
        self.store.upsert(manifest, chunks, vectors)
        if self.store.count(manifest.collection_name) != len(chunks):
            return manifest.model_copy(update={"status": ManifestStatus.FAILED})
        if (
            smoke_vector is not None
            and chunks
            and not self.store.search(manifest.collection_name, smoke_vector, chunks[0].scope, 1)
        ):
            return manifest.model_copy(update={"status": ManifestStatus.FAILED})
        self.store.activate(manifest.alias, manifest.collection_name)
        active = manifest.model_copy(
            update={"status": ManifestStatus.ACTIVE, "point_count": len(chunks)}
        )
        self.store.manifests[manifest.collection_name] = active
        if self.store.repository:
            self.store.repository.save_manifest(active)
        return active
