#!/usr/bin/env python3
"""Remove outdated files based on KEEP_DAYS from config."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from config_utils import load_config
from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

cfg = load_config()
KEEP_DAYS = getattr(cfg, "KEEP_DAYS", 7)

RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")
LOTS_DIR = Path("data/lots")


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
    for md in RAW_DIR.rglob("*.md"):
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
            caption = file.with_suffix(".caption.md")
            if not caption.exists():
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
        try:
            data = json.loads(path.read_text())
        except Exception:
            log.warning("Bad lot file", file=str(path))
            continue
        items = data if isinstance(data, list) else [data]
        src = items[0].get("source:path")
        if src and not (RAW_DIR / src).exists():
            path.unlink()
            log.info("Deleted lot", file=str(path))
            count += 1
    if count:
        log.info("Removed stale lots", count=count)


def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    _clean_raw(cutoff)
    _clean_media(cutoff)
    _clean_lots()


if __name__ == "__main__":
    main()

