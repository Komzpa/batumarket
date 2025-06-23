"""Background caption and chopping queue used by :mod:`tg_client.save`."""

from __future__ import annotations

import asyncio
from moderation import should_skip_message
from . import MEDIA_DIR

import os
import subprocess
import sys
import time
from pathlib import Path

from log_utils import get_logger

from . import CHOP_CHECK_INTERVAL, CHOP_COOLDOWN

log = get_logger().bind(module=__name__)

_CHOP_QUEUE: dict[Path, dict[str, object]] = {}
_chop_task: asyncio.Task | None = None


def schedule_caption(path: Path) -> None:
    """Run captioning in a separate process."""

    try:
        subprocess.Popen([sys.executable, "src/caption.py", str(path)])
        log.debug("Caption scheduled", file=str(path))
    except Exception:
        log.exception("Failed to schedule caption", file=str(path))


def schedule_chop(msg_path: Path) -> None:
    """Run lot extraction in a separate process."""

    if os.getenv("TEST_MODE") == "1":
        log.debug("Skip chop in test mode", file=str(msg_path))
        return
    try:
        subprocess.Popen([sys.executable, "src/chop.py", str(msg_path)])
        log.debug("Chop scheduled", file=str(msg_path))
    except Exception:
        log.exception("Failed to schedule chop", file=str(msg_path))


def enqueue_chop(path: Path, meta: dict, text: str) -> None:
    """Queue ``path`` for chopping once captions are available."""
    if should_skip_message(meta, text):
        log.debug("Skipping chop due to moderation", file=str(path))
        return
    files = meta.get("files", [])
    pending: set[Path] = set()
    for rel in files:
        p = MEDIA_DIR / rel
        if p.suffix.lower().startswith(".jpg") or p.suffix.lower() in {".png", ".gif", ".webp"}:
            if not p.with_suffix(".caption.md").exists():
                pending.add(p)
    entry = _CHOP_QUEUE.get(path)
    if entry:
        entry["pending"].update(pending)
        entry["timestamp"] = time.monotonic()
    else:
        _CHOP_QUEUE[path] = {"timestamp": time.monotonic(), "pending": pending}
    log.debug("Queued chop", file=str(path), pending=len(pending), queue=len(_CHOP_QUEUE))
    start_worker()


def start_worker() -> None:
    """Ensure the chop queue worker is running."""

    global _chop_task
    if _chop_task is None or _chop_task.done():
        log.debug("Starting chop worker", queue=len(_CHOP_QUEUE))
        _chop_task = asyncio.create_task(worker())


def process_queue() -> None:
    """Check queued posts and chop cooled down ones."""

    now = time.monotonic()
    for path, item in list(_CHOP_QUEUE.items()):
        pending = {p for p in item["pending"] if not p.with_suffix(".caption.md").exists()}
        item["pending"] = pending
        if not pending and now - item["timestamp"] >= CHOP_COOLDOWN:
            log.debug("Chop cooldown complete", file=str(path))
            schedule_chop(path)
            del _CHOP_QUEUE[path]


async def worker() -> None:
    """Background task processing ``_CHOP_QUEUE``."""

    while _CHOP_QUEUE:
        log.debug("Chop worker tick", queue=len(_CHOP_QUEUE))
        process_queue()
        if not _CHOP_QUEUE:
            break
        await asyncio.sleep(CHOP_CHECK_INTERVAL)


async def flush_queue() -> None:
    """Run the chop worker until the queue is empty and cancel it."""

    global _chop_task
    if _chop_task is None:
        return
    log.debug("Flushing chop queue", queue=len(_CHOP_QUEUE))
    while _CHOP_QUEUE:
        process_queue()
        if not _CHOP_QUEUE:
            break
        await asyncio.sleep(CHOP_CHECK_INTERVAL)
    if _chop_task:
        _chop_task.cancel()
        try:
            await _chop_task
        except asyncio.CancelledError:
            pass
        _chop_task = None
