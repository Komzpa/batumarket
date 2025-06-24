#!/usr/bin/env python3
"""Remove outdated files based on KEEP_DAYS from config."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from config_utils import load_config
from log_utils import get_logger, install_excepthook
from lot_io import read_lots, TRANSLATION_FIELDS
from post_io import raw_post_path, RAW_DIR
from caption_io import has_caption

log = get_logger().bind(script=__file__)
install_excepthook(log)

cfg = load_config()
KEEP_DAYS = getattr(cfg, "KEEP_DAYS", 7)

MEDIA_DIR = Path("data/media")
LOTS_DIR = Path("data/lots")
EMBED_DIR = Path("data/embeddings")


def _parse_date(md: Path) -> datetime | None:
    """Return the ``date`` field from a markdown file if present."""
    try:
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("date: "):
                ts = datetime.fromisoformat(line[6:])
                return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except Exception:
        log.debug("Failed to read date", file=str(md))
    return None


def _clean_raw(cutoff: datetime) -> None:
    count = 0
    if not RAW_DIR.exists():
        return
    for md in raw_post_path(Path(), RAW_DIR).rglob("*.md"):
        ts = _parse_date(md)
        if ts and ts < cutoff:
            md.unlink()
            count += 1
            log.info("Deleted raw post", file=str(md))
    if count:
        log.info("Removed old posts", count=count)


def _clean_media(cutoff: datetime) -> None:
    count = 0
    if not MEDIA_DIR.exists():
        return
    for md in MEDIA_DIR.rglob("*.md"):
        ts = _parse_date(md)
        if ts and ts < cutoff:
            file = md.with_suffix("")
            if not has_caption(file):
                for p in [file, md]:
                    if p.exists():
                        p.unlink()
                        log.info("Deleted media", file=str(p))
                count += 1
    if count:
        log.info("Removed old media", count=count)


def _clean_lots() -> None:
    count = 0
    if not LOTS_DIR.exists():
        return
    for path in LOTS_DIR.rglob("*.json"):
        items = read_lots(path)
        if not items:
            log.warning("Bad lot file", file=str(path))
            continue
        missing = any(not lot.get(f) for lot in items for f in TRANSLATION_FIELDS)
        flagged = any(l.get("fraud") is not None for l in items)
        # Keep lots flagged as fraud even when translations are missing so
        # potential scams remain available for manual review.
        if missing and not flagged:
            path.unlink()
            log.info("Deleted lot", file=str(path), reason="missing translations")
            count += 1
            continue
        src = items[0].get("source:path")
        if src and not raw_post_path(src, RAW_DIR).exists():
            path.unlink()
            log.info("Deleted lot", file=str(path))
            count += 1
    if count:
        log.info("Removed stale lots", count=count)


def _clean_embeddings() -> None:
    """Delete embedding files when the matching lot JSON is absent."""
    count = 0
    if not EMBED_DIR.exists():
        return
    for path in EMBED_DIR.rglob("*.json"):
        lot = LOTS_DIR / path.relative_to(EMBED_DIR)
        if not lot.exists():
            path.unlink()
            log.info("Deleted embedding", file=str(path))
            count += 1
    if count:
        log.info("Removed orphan embeddings", count=count)


def _remove_empty_dirs(root: Path) -> None:
    """Recursively remove empty folders under ``root``."""
    count = 0
    if not root.exists():
        return
    # walk bottom up so parent dirs are removed after their children
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            log.debug("Removed empty dir", path=str(path))
            count += 1
    if count:
        log.info("Removed empty dirs", count=count)


def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    _clean_raw(cutoff)
    _clean_media(cutoff)
    _clean_lots()
    _clean_embeddings()
    for root in [RAW_DIR, MEDIA_DIR, LOTS_DIR, EMBED_DIR]:
        _remove_empty_dirs(root)


if __name__ == "__main__":
    main()

