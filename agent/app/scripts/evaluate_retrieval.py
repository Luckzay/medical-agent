from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models.evidence import LiteratureSearchInput
from app.services.evidence_store import EvidenceStore


def evaluate(source: Path, evidence_database: Path, fixture: Path) -> dict[str, object]:
    specification = json.loads(fixture.read_text(encoding="utf-8"))
    store = EvidenceStore(source, evidence_database)
    cases: list[dict[str, object]] = []
    try:
        for case in specification["cases"]:
            result = store.search(LiteratureSearchInput(query=case["query"], top_k=10))
            count = len(result.hits)
            passed = count >= case.get("expected_min_hits", 0) and count <= case.get(
                "expected_max_hits", 10
            )
            cases.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "hits": count,
                    "top_ids": [hit.document_id for hit in result.hits],
                    "passed": passed,
                }
            )
    finally:
        store.close()
    passed_count = sum(bool(case["passed"]) for case in cases)
    return {
        "fixture_version": specification["version"],
        "lexical": {
            "cases": len(cases),
            "passed": passed_count,
            "pass_rate": round(passed_count / len(cases), 6),
        },
        "candidate_hybrid": {
            "enabled": False,
            "reason": (
                "production embedding model not evaluated; deterministic test embedding "
                "is non-semantic"
            ),
        },
        "cases": cases,
        "rollout_gate_passed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence-database", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            evaluate(args.source, args.evidence_database, args.fixture),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
