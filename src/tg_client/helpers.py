"""Utility helpers for :mod:`tg_client`."""

from __future__ import annotations

from pathlib import Path
import asyncio

from log_utils import get_logger
from post_io import write_post

from . import RAW_DIR, PROGRESS_INTERVAL

log = get_logger().bind(module=__name__)

# Grouped messages are merged into a single Markdown file. ``_GROUPS`` maps
# album id to the path where the combined message is stored. ``_GROUP_CACHE``
# caches lookups per chat so albums can be resumed quickly.
_GROUPS: dict[int, Path] = {}
_GROUP_CACHE: dict[str, dict[int, Path]] = {}


def progress_logger(chat: str, msg_id: int):
    """Return a progress callback that logs received bytes."""

    last = 0.0

    def cb(received: int, total: int) -> None:
        nonlocal last
        now = asyncio.get_event_loop().time()
        if now - last >= PROGRESS_INTERVAL:
            last = now
            log.info(
                "Downloading", chat=chat, id=msg_id, received=received, total=total
            )

    return cb


def write_md(path: Path, meta: dict, body: str) -> None:
    """Store a raw post in Markdown format."""

    write_post(path, meta, body)


def scan_group_cache(chat: str) -> dict[int, Path]:
    """Build group_id -> Path mapping for ``chat`` quickly."""

    chat_dir = RAW_DIR / chat
    groups: dict[int, Path] = {}
    if not chat_dir.exists():
        return groups
    for p in chat_dir.rglob("*.md"):
        try:
            with p.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        break
                    if line.startswith("group_id:"):
                        val = line.split(":", 1)[1].strip()
                        if val.isdigit():
                            groups[int(val)] = p
                        break
        except Exception:
            log.debug("Failed to read group id", file=str(p))
    log.debug("Scanned groups", chat=chat, groups=len(groups))
    return groups


def find_group_path(chat: str, group_id: int) -> Path | None:
    """Return stored message path for ``group_id`` if known."""

    groups = _GROUP_CACHE.get(chat)
    if groups is None:
        groups = scan_group_cache(chat)
        _GROUP_CACHE[chat] = groups
    return groups.get(group_id)


def get_message_path(chat: str, msg_id: int) -> Path | None:
    """Return path of stored message ``msg_id`` in ``chat`` if any."""

    for p in (RAW_DIR / chat).rglob(f"{msg_id}.md"):
        return p
    return None
