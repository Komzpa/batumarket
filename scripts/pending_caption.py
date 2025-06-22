#!/usr/bin/env python3
"""List images that need captions."""
from pathlib import Path
import sys

MEDIA_DIR = Path("data/media")


def main() -> None:
    files = sorted(
        (p for p in MEDIA_DIR.rglob("*") if p.is_file() and p.suffix != ".md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        if not path.with_suffix(".caption.md").exists():
            sys.stdout.write(str(path))
            sys.stdout.write("\0")


if __name__ == "__main__":
    main()
