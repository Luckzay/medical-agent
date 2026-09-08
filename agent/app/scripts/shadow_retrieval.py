from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models.evidence import LiteratureSearchInput
from app.services.evidence_store import EvidenceStore


def compare(source: Path, evidence_database: Path, queries: list[str]) -> list[dict[str, object]]:
    store = EvidenceStore(source, evidence_database)
    try:
        output: list[dict[str, object]] = []
        for query in queries:
            lexical = store.search(LiteratureSearchInput(query=query, top_k=10))
            output.append(
                {
                    "query": query,
                    "agent_visible_ids": [hit.document_id for hit in lexical.hits],
                    "lexical_ids": [hit.document_id for hit in lexical.hits],
                    "hybrid_ids": [],
                    "hybrid_available": False,
                    "agent_results_changed": False,
                    "degraded_reason": "vector_disabled",
                }
            )
        return output
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare lexical and candidate hybrid retrieval in shadow mode"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence-database", type=Path, required=True)
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(
        compare(args.source, args.evidence_database, args.query), ensure_ascii=False, indent=2
    )
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
