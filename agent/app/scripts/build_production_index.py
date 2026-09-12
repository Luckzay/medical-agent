from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the app package is in the path
sys.path.append(str(Path(__file__).parents[2]))

from app.scripts.build_toxicology_index import main as build_toxicology


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production index build entry point (Toxicology)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force rebuild even if snapshot is unchanged"
    )
    # Compatibility with old arguments (ignored)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--top-k", type=int, default=3)

    args = parser.parse_args()

    # In production, we always delegate to the MySQL-based toxicology index builder.
    # The --source argument is no longer used as data comes from MySQL.

    sys.argv = [sys.argv[0]]
    if args.force:
        sys.argv.append("--force")

    build_toxicology()


if __name__ == "__main__":
    main()
