#!/usr/bin/env python3
"""List lot JSON files needing embeddings and upgrade legacy vectors."""
from pathlib import Path
import sys
# Make ``src`` imports work when executing this script directly from the
# repository root as done in the Makefile.  Unit tests set ``PYTHONPATH``
# explicitly so this is only needed for manual runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lot_io import read_lots, embedding_path
from serde_utils import load_json, write_json
from log_utils import get_logger
from moderation import should_skip_message, should_skip_lot
from post_io import read_post, raw_post_path_from_lot

LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")
RAW_DIR = Path("data/raw")

log = get_logger().bind(script=__file__)


def _needs_embedding(path: Path, emb: Path, lots: list[dict]) -> bool:
    """Return ``True`` when ``emb`` is missing or out of date.

    The function upgrades older embedding files written as a single object and
    deletes mismatched files.
    """
    if not emb.exists():
        return True
    if emb.stat().st_mtime < path.stat().st_mtime:
        return True
    data = load_json(emb)
    if data is None:
        emb.unlink(missing_ok=True)
        log.debug("Bad embedding file", file=str(emb))
        return True
    # Legacy format stored a single {id, vec} object per file
    if isinstance(data, dict) and "id" in data and "vec" in data:
        if len(lots) == 1:
            write_json(emb, [data])
            log.debug("Upgraded embedding", file=str(emb))
            return False
        emb.unlink(missing_ok=True)
        log.debug(
            "Embedding count mismatch", file=str(emb), lots=len(lots), vecs=1
        )
        return True
    if isinstance(data, list):
        if len(data) != len(lots):
            emb.unlink(missing_ok=True)
            log.debug(
                "Embedding count mismatch",
                file=str(emb),
                lots=len(lots),
                vecs=len(data),
            )
            return True
        return False
    emb.unlink(missing_ok=True)
    log.debug("Unknown embedding format", file=str(emb))
    return True


def main() -> None:
    if not LOTS_DIR.exists():
        log.error("LOTS_DIR missing", dir=str(LOTS_DIR))
        return

    files = sorted(
        LOTS_DIR.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    pending: list[Path] = []
    for path in files:
        lots = read_lots(path) or []
        if not lots:
            continue
        out = embedding_path(path, VEC_DIR, LOTS_DIR)
        raw = raw_post_path_from_lot(lots[0], RAW_DIR)
        skip = False
        if raw and raw.exists():
            try:
                meta, text = read_post(raw)
                if should_skip_message(meta, text):
                    skip = True
            except Exception:
                log.exception("Failed moderation check", file=str(path))
                continue
        if not skip and any(should_skip_lot(l) for l in lots):
            skip = True
        if skip:
            log.info("Skipping", file=str(path), reason="moderation")
            continue
        if _needs_embedding(path, out, lots):
            pending.append(path)

    for path in pending:
        sys.stdout.write(str(path))
        sys.stdout.write("\0")

    log.info("Pending lots", count=len(pending))


if __name__ == "__main__":
    main()
