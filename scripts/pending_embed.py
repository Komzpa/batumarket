#!/usr/bin/env python3
"""List lot JSON files needing embeddings."""
from pathlib import Path
import sys

LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")


def main() -> None:
    files = sorted(LOTS_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        rel = path.relative_to(LOTS_DIR)
        out = (VEC_DIR / rel).with_suffix(".json")
        if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
            sys.stdout.write(str(path))
            sys.stdout.write("\0")


if __name__ == "__main__":
    main()
