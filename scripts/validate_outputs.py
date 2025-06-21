#!/usr/bin/env python3
"""Validate pipeline outputs for missing pieces.

Checks are split into three categories so each step can verify that the
previous one completed successfully:

- ``captions`` – every image in ``data/media`` has a ``*.caption.md`` file.
- ``lots`` – each message under ``data/raw`` has a corresponding JSON file.
- ``vectors`` – all lot JSON files have up to date embeddings.

Run without arguments to execute every check. The script logs the first
few problems and exits with ``1`` when anything is missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

MEDIA_DIR = Path("data/media")
RAW_DIR = Path("data/raw")
LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")


def _report_missing(kind: str, items: list[Path]) -> None:
    for p in items[:20]:
        log.error(f"Missing {kind}", path=str(p))
    if len(items) > 20:
        log.warning(f"Further missing {kind} omitted", count=len(items) - 20)


def check_captions() -> bool:
    missing: list[Path] = []
    for path in MEDIA_DIR.rglob("*"):
        if not path.is_file() or path.suffix == ".md":
            continue
        if not path.with_suffix(".caption.md").exists():
            missing.append(path)
    if missing:
        _report_missing("caption", missing)
        log.warning("Missing captions", count=len(missing))
        return False
    return True


def check_lots() -> bool:
    missing: list[Path] = []
    for msg in RAW_DIR.rglob("*.md"):
        out = LOTS_DIR / msg.relative_to(RAW_DIR).with_suffix(".json")
        if not out.exists():
            missing.append(msg)
    if missing:
        _report_missing("lot", missing)
        log.warning("Missing lot files", count=len(missing))
        return False
    return True


def check_vectors() -> bool:
    missing: list[Path] = []
    for lot in LOTS_DIR.rglob("*.json"):
        vec = VEC_DIR / lot.relative_to(LOTS_DIR).with_suffix(".json")
        if not vec.exists() or vec.stat().st_mtime < lot.stat().st_mtime:
            missing.append(lot)
    if missing:
        _report_missing("vector", missing)
        log.warning("Missing vectors", count=len(missing))
        return False
    return True


CHECKS = {
    "captions": check_captions,
    "lots": check_lots,
    "vectors": check_vectors,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate pipeline outputs")
    parser.add_argument(
        "checks",
        nargs="*",
        default=list(CHECKS),
        help="checks to run: captions, lots, vectors",
    )
    args = parser.parse_args(argv)

    ok = True
    for name in args.checks:
        func = CHECKS.get(name)
        if not func:
            parser.error(f"Unknown check: {name}")
        ok &= func()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
