from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic

logger = logging.getLogger("medical_agent.knowledge")


class KnowledgeMetrics:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.latencies_ms: dict[str, list[float]] = {}
        self.gauges: dict[str, float] = {}

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    @contextmanager
    def stage(self, name: str, **safe_fields: str) -> Iterator[None]:
        started = monotonic()
        try:
            yield
            status = "ok"
        except Exception:
            status = "failed"
            raise
        finally:
            latency = (monotonic() - started) * 1000
            self.latencies_ms.setdefault(name, []).append(latency)
            logger.info(
                json.dumps(
                    {
                        "event": "knowledge_stage",
                        "stage": name,
                        "status": status,
                        "latency_ms": round(latency, 3),
                        **safe_fields,
                    },
                    sort_keys=True,
                )
            )

    def snapshot(self) -> dict[str, object]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "latencies_ms": {name: values[-100:] for name, values in self.latencies_ms.items()},
        }


metrics = KnowledgeMetrics()
