#!/usr/bin/env python3
"""List message files needing chopping.

Outputs NUL-separated paths sorted by modification time descending.
"""
from pathlib import Path
import sys

RAW_DIR = Path("data/raw")
LOTS_DIR = Path("data/lots")


def main() -> None:
    files = sorted(RAW_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for msg in files:
        rel = msg.relative_to(RAW_DIR)
        out = LOTS_DIR / rel.with_suffix(".json")
        if not out.exists():
            sys.stdout.write(str(msg))
            sys.stdout.write("\0")


if __name__ == "__main__":
    main()
