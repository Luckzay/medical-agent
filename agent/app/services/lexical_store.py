from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from elasticsearch import Elasticsearch, NotFoundError

from app.models.knowledge import OwnershipScope


class LexicalStoreError(RuntimeError):
    """Normalized lexical backend failure without leaking credentials or response bodies."""


@dataclass(frozen=True)
class RetrievalCandidate:
    identifier: str
    score: float
    exact_fields: tuple[str, ...] = ()
    source: str = "lexical"
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LexicalSearchResult:
    candidates: list[RetrievalCandidate]
    backend: str
    source_snapshot: str | None = None
    degraded_reason: str | None = None


@runtime_checkable
class LexicalStore(Protocol):
    backend: str

    def health(self) -> dict[str, object]: ...

    def search(
        self,
        query: str,
        scope: OwnershipScope,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> LexicalSearchResult: ...


class ElasticsearchLexicalStore:
    backend = "elasticsearch"
    schema_version = 1
    _safe_generation = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(
        self,
        client: Elasticsearch,
        alias: str,
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.client = client.options(request_timeout=timeout_seconds)
        self.alias = alias
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def mapping() -> dict[str, object]:
        text = {
            "type": "text",
            "analyzer": "standard",
            "fields": {"exact": {"type": "keyword", "ignore_above": 512}},
        }
        return {
            "dynamic": "strict",
            "properties": {
                "reference": {"type": "keyword"},
                "herb_id": {"type": "long"},
                "tenant_id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "source_snapshot": {"type": "keyword"},
                "name": text,
                "common_name": text,
                "virulence": text,
                "toxicity_mechanism": text,
                "pathological_examination": text,
                "crowd_taboo": text,
                "symptom_contraindications": text,
                "adr": text,
                "typical_cases_of_adr": text,
                "clinical_suggestion": text,
                "clinical_suggestion_basis": text,
                "compound_names": text,
                "cas_numbers": {"type": "keyword"},
                "formulas": {"type": "keyword"},
            },
        }

    def versioned_index(self, generation: str, snapshot: str) -> str:
        if not self._safe_generation.fullmatch(generation):
            raise ValueError("invalid Elasticsearch generation")
        return f"{self.alias}_v{generation}_{snapshot[:8]}".lower()

    def health(self) -> dict[str, object]:
        try:
            info = self.client.info()
            cluster = self.client.cluster.health()
            return {
                "available": True,
                "backend": self.backend,
                "version": info.get("version", {}).get("number"),
                "cluster_status": cluster.get("status"),
                "alias": self.alias,
            }
        except Exception as exc:
            return {"available": False, "backend": self.backend, "reason": type(exc).__name__}

    def create_versioned_index(self, index: str, snapshot: str) -> None:
        try:
            mappings = self.mapping()
            mappings["_meta"] = {
                "schema_version": self.schema_version,
                "source_snapshot": snapshot,
            }
            self.client.indices.create(
                index=index,
                mappings=mappings,
                settings={
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                },
            )
        except Exception as exc:
            raise LexicalStoreError(
                f"elasticsearch index creation failed: {type(exc).__name__}"
            ) from exc

    def bulk_index(self, index: str, documents: Iterable[Mapping[str, object]]) -> int:
        operations: list[dict[str, object]] = []
        expected_ids: list[str] = []
        for document in documents:
            identifier = str(document["reference"])
            expected_ids.append(identifier)
            operations.extend(({"index": {"_index": index, "_id": identifier}}, dict(document)))
        if not operations:
            return 0
        try:
            response = self.client.bulk(
                operations=operations,
                refresh="wait_for",
            )
        except Exception as exc:
            raise LexicalStoreError(
                f"elasticsearch bulk request failed: {type(exc).__name__}"
            ) from exc
        items = response.get("items", [])
        failures = []
        for expected_id, item in zip(expected_ids, items, strict=False):
            result = item.get("index", {})
            if result.get("error") or int(result.get("status", 500)) >= 300:
                failures.append(expected_id)
        if len(items) != len(expected_ids):
            failures.extend(expected_ids[len(items) :])
        if failures:
            raise LexicalStoreError(
                f"elasticsearch bulk indexing failed for {len(failures)} document(s): "
                + ",".join(failures[:5])
            )
        return len(items)

    def activate(self, index: str) -> None:
        try:
            current: Mapping[str, Any]
            try:
                current = dict(self.client.indices.get_alias(name=self.alias))
            except NotFoundError:
                current = {}
            actions = [
                {"remove": {"index": old, "alias": self.alias}} for old in current if old != index
            ]
            actions.append({"add": {"index": index, "alias": self.alias}})
            self.client.indices.update_aliases(actions=actions)
        except Exception as exc:
            raise LexicalStoreError(
                f"elasticsearch alias switch failed: {type(exc).__name__}"
            ) from exc

    def count(self, index: str) -> int:
        try:
            return int(self.client.count(index=index)["count"])
        except Exception as exc:
            raise LexicalStoreError(f"elasticsearch count failed: {type(exc).__name__}") from exc

    def document_ids(self, index: str, limit: int = 10_000) -> set[str]:
        try:
            response = self.client.search(
                index=index,
                query={"match_all": {}},
                size=limit,
                source=False,
            )
            return {str(hit["_id"]) for hit in response["hits"]["hits"]}
        except Exception as exc:
            raise LexicalStoreError(
                f"elasticsearch id reconciliation failed: {type(exc).__name__}"
            ) from exc

    def search(
        self,
        query: str,
        scope: OwnershipScope,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> LexicalSearchResult:
        filter_clauses: list[dict[str, object]] = [
            {"term": {"tenant_id": scope.tenant_id}},
            {"term": {"project_id": scope.project_id}},
        ]
        allowed_filters = {"herb_id", "reference", "source_snapshot"}
        for key, value in (filters or {}).items():
            if key not in allowed_filters:
                raise ValueError(f"unsupported lexical filter: {key}")
            filter_clauses.append({"term": {key: value}})
        exact_fields = {
            "name.exact": 20.0,
            "common_name.exact": 15.0,
            "compound_names.exact": 18.0,
            "cas_numbers": 30.0,
            "formulas": 25.0,
        }
        should: list[dict[str, object]] = [
            {"term": {field: {"value": query, "boost": boost}}}
            for field, boost in exact_fields.items()
        ]
        should.append(
            {
                "multi_match": {
                    "query": query,
                    "type": "best_fields",
                    "operator": "or",
                    "fields": [
                        "name^8",
                        "common_name^6",
                        "compound_names^7",
                        "toxicity_mechanism^3",
                        "virulence^3",
                        "symptom_contraindications^2",
                        "adr^2",
                        "clinical_suggestion^2",
                        "clinical_suggestion_basis",
                        "pathological_examination",
                        "crowd_taboo",
                        "typical_cases_of_adr",
                    ],
                }
            }
        )
        try:
            response = self.client.search(
                index=self.alias,
                query={
                    "bool": {"filter": filter_clauses, "should": should, "minimum_should_match": 1}
                },
                size=limit,
                source_includes=[
                    "reference",
                    "source_snapshot",
                    *[field.split(".")[0] for field in exact_fields],
                ],
            )
        except Exception as exc:
            raise LexicalStoreError(f"elasticsearch search failed: {type(exc).__name__}") from exc
        candidates: list[RetrievalCandidate] = []
        snapshot: str | None = None
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            snapshot = snapshot or source.get("source_snapshot")
            exact = tuple(
                field.split(".")[0]
                for field in exact_fields
                if query in _as_strings(source.get(field.split(".")[0]))
            )
            candidates.append(
                RetrievalCandidate(
                    identifier=str(source.get("reference", hit.get("_id"))),
                    score=float(hit.get("_score") or 0.0),
                    exact_fields=exact,
                    source=self.backend,
                    payload=source,
                )
            )
        return LexicalSearchResult(candidates, self.backend, snapshot)


def _as_strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Sequence):
        return {str(item) for item in value}
    return set()
