from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import Any, Protocol


class RerankerProvider(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class RerankerError(RuntimeError):
    pass


class RequiredRerankerError(RerankerError):
    pass


def validate_scores(raw: Sequence[float], expected: int) -> list[float]:
    if len(raw) != expected:
        raise RerankerError("reranker score count mismatch")
    scores = [float(value) for value in raw]
    if not all(math.isfinite(value) for value in scores):
        raise RerankerError("reranker returned a non-finite score")
    return scores


class DisabledReranker:
    @property
    def fingerprint(self) -> str:
        return "disabled"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        del query
        return [0.0] * len(passages)


class DeterministicTestReranker:
    """Token-overlap scorer for deterministic tests; not a quality model."""

    @property
    def fingerprint(self) -> str:
        return "deterministic-test:token-overlap:v1"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        query_tokens = frozenset(query.casefold().split())
        raw = [float(len(query_tokens.intersection(text.casefold().split()))) for text in passages]
        return validate_scores(raw, len(passages))


class LazyCrossEncoderReranker:
    def __init__(
        self,
        model: str,
        revision: str,
        *,
        device: str = "cpu",
        batch_size: int = 16,
        loader: Callable[[], Any] | None = None,
    ) -> None:
        self.model = model
        self.revision = revision
        self.device = device
        self.batch_size = batch_size
        self._loader = loader
        self._instance: Any | None = None

    @property
    def fingerprint(self) -> str:
        return f"sentence-transformers-cross-encoder:{self.model}@{self.revision}"

    @property
    def loaded(self) -> bool:
        return self._instance is not None

    def _load(self) -> Any:
        if self._instance is None:
            if self._loader is not None:
                self._instance = self._loader()
            else:
                module = importlib.import_module("sentence_transformers")
                self._instance = module.CrossEncoder(
                    self.model, revision=self.revision, device=self.device
                )
        return self._instance

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, passage) for passage in passages]
        try:
            raw = self._load().predict(pairs, batch_size=self.batch_size)
        except Exception as exc:
            raise RerankerError("cross-encoder reranking failed") from exc
        values = raw.tolist() if hasattr(raw, "tolist") else raw
        return validate_scores(values, len(passages))


@lru_cache(maxsize=8)
def cached_reranker(
    provider: str, model: str, revision: str, device: str, batch_size: int
) -> RerankerProvider:
    if provider == "disabled":
        return DisabledReranker()
    if provider == "deterministic_test":
        return DeterministicTestReranker()
    if provider == "cross_encoder":
        return LazyCrossEncoderReranker(
            model, revision, device=device, batch_size=batch_size
        )
    raise ValueError(f"unsupported reranker provider: {provider}")
