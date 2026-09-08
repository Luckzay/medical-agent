from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge import OwnershipScope


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RelevanceJudgment(StrictModel):
    evidence_id: str = Field(min_length=1)
    grade: int = Field(ge=0, le=3)


class AnnotationProvenance(StrictModel):
    label_type: Literal["human", "weak", "synthetic"]
    method: str = Field(min_length=1)
    annotator: str = Field(min_length=1)
    annotated_at: str = Field(min_length=1)
    notes: str | None = None


class GoldenQuery(StrictModel):
    query_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    query_zh: str = Field(min_length=1)
    query_en: str = Field(min_length=1)
    research_goal: str = Field(min_length=1)
    scope: OwnershipScope
    relevant_evidence: tuple[RelevanceJudgment, ...] = Field(min_length=1)
    hard_negatives: tuple[str, ...] = ()
    tags: tuple[str, ...] = Field(min_length=1)
    provenance: AnnotationProvenance

    @model_validator(mode="after")
    def validate_judgments(self) -> GoldenQuery:
        ids = [item.evidence_id for item in self.relevant_evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence judgment")
        if len(self.hard_negatives) != len(set(self.hard_negatives)):
            raise ValueError("duplicate hard negative")
        positive = {item.evidence_id for item in self.relevant_evidence if item.grade > 0}
        if positive.intersection(self.hard_negatives):
            raise ValueError("positive evidence cannot also be a hard negative")
        return self


class GoldenDataset(StrictModel):
    schema_version: Literal["golden-retrieval-v1"]
    dataset_id: str = Field(min_length=1)
    corpus_fingerprint: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    description: str = Field(min_length=1)
    queries: tuple[GoldenQuery, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_queries(self) -> GoldenDataset:
        ids = [item.query_id for item in self.queries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate query_id")
        return self

    @property
    def sha256(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def is_weak(self) -> bool:
        return any(item.provenance.label_type != "human" for item in self.queries)


def load_dataset(path: str | Path) -> GoldenDataset:
    return GoldenDataset.model_validate_json(Path(path).read_text(encoding="utf-8"), strict=True)


def save_dataset(dataset: GoldenDataset, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def add_human_judgment(
    dataset: GoldenDataset,
    query_id: str,
    judgments: Sequence[RelevanceJudgment],
    *,
    annotator: str,
    method: str,
    annotated_at: str | None = None,
) -> GoldenDataset:
    updated: list[GoldenQuery] = []
    found = False
    for query in dataset.queries:
        if query.query_id != query_id:
            updated.append(query)
            continue
        found = True
        updated.append(
            query.model_copy(
                update={
                    "relevant_evidence": tuple(judgments),
                    "provenance": AnnotationProvenance(
                        label_type="human",
                        method=method,
                        annotator=annotator,
                        annotated_at=annotated_at or datetime.now().astimezone().isoformat(),
                    ),
                }
            )
        )
    if not found:
        raise KeyError(query_id)
    return GoldenDataset.model_validate(
        {**dataset.model_dump(mode="python"), "queries": tuple(updated)}, strict=True
    )


def recall_at(ranking: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    relevant = {identifier for identifier, grade in grades.items() if grade > 0}
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranking[:k])) / len(relevant)


def precision_at(ranking: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(grades.get(identifier, 0) > 0 for identifier in ranking[:k]) / k


def mrr_at(ranking: Sequence[str], grades: Mapping[str, int], k: int = 10) -> float:
    for rank, identifier in enumerate(ranking[:k], 1):
        if grades.get(identifier, 0) > 0:
            return 1.0 / rank
    return 0.0


def ndcg_at(ranking: Sequence[str], grades: Mapping[str, int], k: int = 10) -> float:
    def gain(values: Sequence[int]) -> float:
        return float(
            sum(
                (2**grade - 1) / math.log2(rank + 1)
                for rank, grade in enumerate(values, 1)
            )
        )

    actual = gain([grades.get(identifier, 0) for identifier in ranking[:k]])
    ideal = gain(sorted(grades.values(), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def irrelevant_rate(ranking: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    selected = ranking[:k]
    if not selected:
        return 0.0
    return sum(
        identifier in grades and grades[identifier] == 0 for identifier in selected
    ) / len(selected)


class RetrievalRun(StrictModel):
    evidence_ids: tuple[str, ...]
    latency_ms: float = Field(ge=0)
    broken_lineage: int = Field(default=0, ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BenchmarkBackend(Protocol):
    def retrieve(
        self,
        mode: str,
        query: GoldenQuery,
        parameters: Mapping[str, Any],
    ) -> RetrievalRun: ...


class ModeReport(StrictModel):
    status: Literal["completed", "not_run", "failed"]
    metrics: dict[str, float] = Field(default_factory=dict)
    per_query: dict[str, RetrievalRun] = Field(default_factory=dict)
    reason: str | None = None


class BenchmarkReport(StrictModel):
    report_version: Literal["rag-benchmark-v1"] = "rag-benchmark-v1"
    dataset_id: str
    dataset_sha256: str
    weak_label_warning: str | None
    model_fingerprint: str
    collection_alias: str
    collection_generation: str
    parameters: dict[str, Any]
    random_seed: int
    modes: dict[str, ModeReport]
    candidate_models: dict[str, str] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = ["# RAG 离线评测报告", ""]
        if self.weak_label_warning:
            lines.extend([f"> **警告：{self.weak_label_warning}**", ""])
        lines.extend(
            [
                f"- Dataset: `{self.dataset_id}` / `{self.dataset_sha256}`",
                f"- Model: `{self.model_fingerprint}`",
                f"- Collection: `{self.collection_alias}` / `{self.collection_generation}`",
                f"- Seed: `{self.random_seed}`",
                "",
                "| Mode | Status | Recall@10 | MRR@10 | nDCG@10 | Avg/P95 ms |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for name, result in self.modes.items():
            metric = result.metrics
            latency = f"{metric.get('latency_avg_ms', 0):.3f}/{metric.get('latency_p95_ms', 0):.3f}"
            lines.append(
                f"| {name} | {result.status} | {metric.get('recall@10', 0):.4f} | "
                f"{metric.get('mrr@10', 0):.4f} | {metric.get('ndcg@10', 0):.4f} | {latency} |"
            )
        lines.extend(["", "## 候选模型状态", ""])
        for model, status in self.candidate_models.items():
            lines.append(f"- `{model}`: `{status}`")
        lines.extend(["", "未实际运行的候选模型不包含成绩。", ""])
        return "\n".join(lines)


MODES = ("lexical", "vector", "hybrid_rrf", "hybrid_reranker")
KS = (1, 3, 5, 10)


def _percentile_95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def run_benchmark(
    dataset: GoldenDataset,
    backend: BenchmarkBackend,
    *,
    model_fingerprint: str,
    collection_alias: str,
    collection_generation: str,
    parameters: Mapping[str, Any],
    random_seed: int = 20260809,
    modes: Sequence[str] = MODES,
    candidate_models: Mapping[str, str] | None = None,
) -> BenchmarkReport:
    random.seed(random_seed)
    reports: dict[str, ModeReport] = {}
    for mode in modes:
        runs: dict[str, RetrievalRun] = {}
        values: dict[str, list[float]] = {
            **{f"recall@{k}": [] for k in KS},
            **{f"precision@{k}": [] for k in KS},
            "mrr@10": [],
            "ndcg@10": [],
            "irrelevant_rate@10": [],
            "broken_lineage_rate": [],
        }
        for query in dataset.queries:
            run = backend.retrieve(mode, query, parameters)
            runs[query.query_id] = run
            grades = {item.evidence_id: item.grade for item in query.relevant_evidence}
            grades.update({identifier: 0 for identifier in query.hard_negatives})
            for k in KS:
                values[f"recall@{k}"].append(recall_at(run.evidence_ids, grades, k))
                values[f"precision@{k}"].append(precision_at(run.evidence_ids, grades, k))
            values["mrr@10"].append(mrr_at(run.evidence_ids, grades))
            values["ndcg@10"].append(ndcg_at(run.evidence_ids, grades))
            values["irrelevant_rate@10"].append(
                irrelevant_rate(run.evidence_ids, grades, 10)
            )
            denominator = len(run.evidence_ids) + run.broken_lineage
            values["broken_lineage_rate"].append(
                run.broken_lineage / denominator if denominator else 0.0
            )
        latencies = [run.latency_ms for run in runs.values()]
        metrics = {name: statistics.fmean(metric) for name, metric in values.items()}
        metrics["latency_avg_ms"] = statistics.fmean(latencies) if latencies else 0.0
        metrics["latency_p95_ms"] = _percentile_95(latencies)
        reports[mode] = ModeReport(status="completed", metrics=metrics, per_query=runs)
    return BenchmarkReport(
        dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256,
        weak_label_warning=(
            "当前 seed 含 weak/synthetic 标签，指标仅用于管线基线，不是最终质量结论。"
            if dataset.is_weak
            else None
        ),
        model_fingerprint=model_fingerprint,
        collection_alias=collection_alias,
        collection_generation=collection_generation,
        parameters=dict(parameters),
        random_seed=random_seed,
        modes=reports,
        candidate_models=dict(candidate_models or {}),
    )


def collection_generation_key(fingerprint: str, dimension: int, corpus_hash: str) -> str:
    payload = f"{fingerprint}|d={dimension}|{corpus_hash}".encode()
    return f"gen-{hashlib.sha256(payload).hexdigest()[:16]}-d{dimension}"


class EmbeddingCache:
    def __init__(self, path: str | Path, fingerprint: str, dimension: int) -> None:
        self.path = Path(path)
        self.fingerprint = fingerprint
        self.dimension = dimension
        self._values: dict[str, list[float]] = {}
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("fingerprint") != fingerprint or payload.get("dimension") != dimension:
                raise ValueError("embedding cache fingerprint or dimension mismatch")
            self._values = payload.get("values", {})

    def key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def get(self, text: str) -> list[float] | None:
        return self._values.get(self.key(text))

    def put(self, text: str, vector: Sequence[float]) -> None:
        values = [float(item) for item in vector]
        if len(values) != self.dimension or not all(math.isfinite(item) for item in values):
            raise ValueError("invalid cached embedding")
        self._values[self.key(text)] = values

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprint": self.fingerprint,
            "dimension": self.dimension,
            "values": self._values,
        }
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def parameter_grid(options: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [{}]
    for name in sorted(options):
        rows = [{**row, name: value} for row in rows for value in options[name]]
    return rows
