from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.services.evidence_store import EvidenceStore


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Rebuild the offline literature evidence index")
    parser.add_argument("--source", type=Path, default=settings.evidence_source_path)
    parser.add_argument("--database", type=Path, default=settings.evidence_database_path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    if arguments.force:
        Path(arguments.database).unlink(missing_ok=True)
    store = EvidenceStore(arguments.source, arguments.database)
    try:
        report = store.quality_report()
        rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        if arguments.report is not None:
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    finally:
        store.close()


if __name__ == "__main__":
    main()
