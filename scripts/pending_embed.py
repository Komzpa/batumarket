#!/usr/bin/env python3
"""List lot JSON files needing embeddings and upgrade legacy vectors."""
from pathlib import Path
import sys
from lot_io import read_lots
from serde_utils import load_json, write_json
from log_utils import get_logger

LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")

log = get_logger().bind(script=__file__)


def _needs_embed(path: Path, vec: Path, lots: list[dict]) -> bool:
    """Return ``True`` when ``vec`` is missing or out of date.

    The function upgrades older vector files written as a single object and
    deletes mismatched files.
    """
    if not vec.exists():
        return True
    if vec.stat().st_mtime < path.stat().st_mtime:
        return True
    data = load_json(vec)
    if data is None:
        vec.unlink(missing_ok=True)
        log.debug("Bad vector file", file=str(vec))
        return True
    # Legacy format stored a single {id, vec} object per file
    if isinstance(data, dict) and "id" in data and "vec" in data:
        if len(lots) == 1:
            write_json(vec, [data])
            log.debug("Upgraded vector", file=str(vec))
            return False
        vec.unlink(missing_ok=True)
        log.debug("Vector count mismatch", file=str(vec), lots=len(lots), vecs=1)
        return True
    if isinstance(data, list):
        if len(data) != len(lots):
            vec.unlink(missing_ok=True)
            log.debug(
                "Vector count mismatch",
                file=str(vec),
                lots=len(lots),
                vecs=len(data),
            )
            return True
        return False
    vec.unlink(missing_ok=True)
    log.debug("Unknown vector format", file=str(vec))
    return True


def main() -> None:
    files = sorted(
        LOTS_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for path in files:
        lots = read_lots(path) or []
        rel = path.relative_to(LOTS_DIR)
        out = (VEC_DIR / rel).with_suffix(".json")
        if _needs_embed(path, out, lots):
            sys.stdout.write(str(path))
            sys.stdout.write("\0")


if __name__ == "__main__":
    main()
