#!/usr/bin/env python3
"""List lot JSON files needing embeddings and upgrade legacy vectors.

The output is fed to ``embed.py`` via GNU Parallel.  Both this script and
``build_site.py`` traverse ``data/lots`` using ``lot_io.iter_lot_files`` so new
lots are discovered in the same order across the pipeline.
"""
from pathlib import Path
import sys
# Make ``src`` imports work when executing this script directly from the
# repository root as done in the Makefile.  Unit tests set ``PYTHONPATH``
# explicitly so this is only needed for manual runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lot_io import read_lots, embedding_path, iter_lot_files
from notes_utils import load_json, write_json
from log_utils import get_logger
from moderation import message_skip_reason, lot_skip_reason
from post_io import read_post, raw_post_path_from_lot

LOTS_DIR = Path("data/lots")
EMBED_DIR = Path("data/embeddings")
RAW_DIR = Path("data/raw")

log = get_logger().bind(script=__file__)


def _needs_embedding(path: Path, emb: Path, lots: list[dict]) -> bool:
    """Return ``True`` when ``emb`` is missing or stale.

    The function also upgrades older vector files stored as a single object and
    removes corrupted or mismatched ones so ``embed.py`` always operates on
    clean data.
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

    # ``embed.py`` expects the newest files first so search results refresh
    # quickly.  ``iter_lot_files`` provides the same ordering used by
    # ``build_site.py`` which keeps both scripts in sync.
    files = iter_lot_files(LOTS_DIR, newest_first=True)
    pending: list[Path] = []
    for path in files:
        lots = read_lots(path) or []
        if not lots:
            continue
        out = embedding_path(path, EMBED_DIR, LOTS_DIR)
        raw = raw_post_path_from_lot(lots[0], RAW_DIR)
        reason = None
        if raw and raw.exists():
            try:
                meta, text = read_post(raw)
                reason = message_skip_reason(meta, text)
            except Exception:
                # Corrupted raw posts should not block embeddings.
                # Log the failure but continue processing the lot.
                log.exception("Failed moderation check", file=str(path))
        if not reason:
            for l in lots:
                lot_reason = lot_skip_reason(l)
                if lot_reason:
                    reason = f"lot:{lot_reason}"
                    break
        if reason:
            log.info("Skipping", file=str(path), reason=reason)
            continue
        # ``_needs_embedding`` checks file timestamps and vector consistency.
        # ``embed.py`` is only invoked when embedding is actually required.
        if _needs_embedding(path, out, lots):
            pending.append(path)

    for path in pending:
        sys.stdout.write(str(path))
        sys.stdout.write("\0")
        sys.stdout.flush()

    log.info("Pending lots", count=len(pending))


if __name__ == "__main__":
    main()
