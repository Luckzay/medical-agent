from __future__ import annotations

import hashlib
import importlib
import math
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def fingerprint(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def health(self) -> dict[str, object]: ...


class EmbeddingValidationError(ValueError):
    pass


def _validate(
    vectors: Sequence[Sequence[float]], expected: int, count: int, normalize: bool
) -> list[list[float]]:
    if len(vectors) != count:
        raise EmbeddingValidationError("embedding count mismatch")
    output: list[list[float]] = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if len(values) != expected or not all(math.isfinite(value) for value in values):
            raise EmbeddingValidationError("invalid embedding dimension or non-finite value")
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            raise EmbeddingValidationError("zero embedding")
        output.append([value / norm for value in values] if normalize else values)
    return output


class DeterministicTestEmbedding:
    """Stable non-semantic test vectors; never suitable for production."""

    def __init__(self, dimension: int = 32, normalize: bool = True) -> None:
        if dimension < 2:
            raise ValueError("dimension must be at least 2")
        self._dimension = dimension
        self.normalize = normalize
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def fingerprint(self) -> str:
        return f"deterministic-test:sha256-expand:v1:d{self.dimension}:norm={self.normalize}"

    def _one(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        return _validate([values[: self.dimension]], self.dimension, 1, self.normalize)[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._one(text)

    def health(self) -> dict[str, object]:
        return {"available": True, "test_only": True, "fingerprint": self.fingerprint}


class LazySentenceTransformerEmbedding:
    def __init__(
        self,
        model: str,
        revision: str,
        dimension: int,
        *,
        normalize: bool = True,
        batch_size: int = 32,
        retries: int = 2,
        timeout_seconds: float = 30,
        device: str = "cpu",
        max_seq_length: int = 512,
        loader: Callable[[], Any] | None = None,
    ) -> None:
        self.model, self.revision, self._dimension = model, revision, dimension
        self.normalize, self.batch_size, self.retries, self.timeout_seconds = (
            normalize,
            batch_size,
            retries,
            timeout_seconds,
        )
        self.device = device
        self.max_seq_length = max_seq_length
        self._loader = loader
        self._instance: Any | None = None

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def fingerprint(self) -> str:
        return (
            f"sentence-transformers:{self.model}@{self.revision}:d{self.dimension}:"
            f"norm={self.normalize}:query=e5"
        )

    def _load(self) -> Any:
        if self._instance is None:
            if self._loader is not None:
                self._instance = self._loader()
            else:
                sentence_transformers = importlib.import_module("sentence_transformers")
                sentence_transformer = sentence_transformers.SentenceTransformer
                self._instance = sentence_transformer(
                    self.model, revision=self.revision, device=self.device
                )
            self._instance.max_seq_length = self.max_seq_length
            dimension_getter = getattr(self._instance, "get_embedding_dimension", None)
            if dimension_getter is None:
                dimension_getter = self._instance.get_sentence_embedding_dimension
            actual = int(dimension_getter())
            if actual != self.dimension:
                self._instance = None
                raise EmbeddingValidationError(
                    f"model dimension {actual} does not match configured {self.dimension}"
                )
        return self._instance

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        last: Exception | None = None
        started = time.monotonic()
        for attempt in range(self.retries + 1):
            try:
                raw = self._load().encode(
                    list(texts), batch_size=self.batch_size, normalize_embeddings=False
                )
                return _validate(
                    raw.tolist() if hasattr(raw, "tolist") else raw,
                    self.dimension,
                    len(texts),
                    self.normalize,
                )
            except Exception as exc:
                last = exc
                if time.monotonic() - started >= self.timeout_seconds or attempt == self.retries:
                    break
                time.sleep(min(0.05 * 2**attempt, 0.5))
        raise RuntimeError("embedding provider failed") from last

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode([f"passage: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]

    def health(self) -> dict[str, object]:
        return {
            "available": self._instance is not None,
            "loaded": self._instance is not None,
            "fingerprint": self.fingerprint,
        }
