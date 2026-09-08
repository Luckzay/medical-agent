from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from app.models.knowledge import (
    CanonicalDocument,
    DocumentChunk,
    DocumentVersion,
    IndexManifest,
    IngestionJob,
    NormalizedBlock,
    OwnershipScope,
)


class UnsupportedMediaTypeError(ValueError):
    def __init__(self, media_type: str) -> None:
        self.media_type = media_type
        super().__init__(f"unsupported media type: {media_type}")


@runtime_checkable
class DocumentParser(Protocol):
    @property
    def media_types(self) -> frozenset[str]: ...

    @property
    def fingerprint(self) -> str: ...

    def parse(self, content: bytes, version_id: str, source_uri: str) -> list[NormalizedBlock]: ...


@runtime_checkable
class DocumentChunker(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def chunk(
        self, blocks: Sequence[NormalizedBlock], scope: OwnershipScope
    ) -> list[DocumentChunk]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def fingerprint(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def health(self) -> dict[str, object]: ...


class VectorCandidate(Protocol):
    @property
    def chunk_id(self) -> str: ...

    @property
    def score(self) -> float: ...


@runtime_checkable
class VectorStore(Protocol):
    def ensure_collection(self, manifest: IndexManifest) -> None: ...

    def upsert(
        self,
        manifest: IndexManifest,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> int: ...

    def search(
        self,
        alias: str,
        vector: Sequence[float],
        scope: OwnershipScope,
        limit: int,
        filters: dict[str, object] | None = None,
    ) -> list[VectorCandidate]: ...

    def delete(self, alias: str, scope: OwnershipScope, **selectors: str) -> int: ...

    def count(self, collection: str, scope: OwnershipScope | None = None) -> int: ...

    def health(self) -> dict[str, object]: ...


@runtime_checkable
class CanonicalRepository(Protocol):
    def create_version(
        self, document: CanonicalDocument, version: DocumentVersion
    ) -> tuple[DocumentVersion, bool]: ...

    def put_blocks(self, scope: OwnershipScope, blocks: Iterable[NormalizedBlock]) -> int: ...

    def put_chunks(self, scope: OwnershipScope, chunks: Iterable[DocumentChunk]) -> int: ...

    def get_chunks(
        self, scope: OwnershipScope, chunk_ids: Sequence[str], *, active_only: bool = True
    ) -> list[DocumentChunk]: ...

    def save_job(self, job: IngestionJob) -> None: ...

    def save_manifest(self, manifest: IndexManifest) -> None: ...
