from __future__ import annotations

"""Telegram client entry point."""

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient, events

from config_utils import load_config
from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

cfg = load_config()
TG_API_ID = cfg.TG_API_ID
TG_API_HASH = cfg.TG_API_HASH
TG_SESSION = cfg.TG_SESSION
KEEP_DAYS = getattr(cfg, "KEEP_DAYS", 7)
DOWNLOAD_WORKERS = getattr(cfg, "DOWNLOAD_WORKERS", 4)

PROGRESS_INTERVAL = 5
DOWNLOAD_TIMEOUT = 300

_last_event = datetime.now(timezone.utc)
_sem: asyncio.Semaphore


def _mark_activity() -> None:
    global _last_event
    _last_event = datetime.now(timezone.utc)


TOPICS: dict[str, list[int]] = {}
_chats: list[str] = []
for item in cfg.CHATS:
    if "/" in item:
        chat, tid_str = item.split("/", 1)
        if chat in TOPICS and TOPICS[chat] is None:
            continue
        try:
            tid = int(tid_str)
        except ValueError:
            log.warning("Ignoring invalid topic id", entry=item)
            continue
        TOPICS.setdefault(chat, []).append(tid)
    else:
        chat = item
        TOPICS[chat] = None
    if chat not in _chats:
        _chats.append(chat)
CHATS = _chats

RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")
STATE_DIR = Path("data/state")
BROKEN_META_FILE = Path("data/ontology/broken_meta.json")
LOTS_DIR = Path("data/lots")

CHOP_COOLDOWN = int(os.getenv("CHOP_COOLDOWN", "20"))
CHOP_CHECK_INTERVAL = 5

_sem = asyncio.Semaphore(DOWNLOAD_WORKERS)

# import submodules after globals so they can reuse them
from . import save as save
from . import sync as sync
from .queue import schedule_caption as _schedule_caption, schedule_chop as _schedule_chop

_should_skip_media = save._should_skip_media
_schedule_caption = _schedule_caption
_schedule_chop = _schedule_chop
_save_media = save._save_media
_save_message = save._save_message
_save_bounded = save._save_bounded
_process_chop_queue = save._process_chop_queue
_flush_chop_queue = save._flush_chop_queue
_GROUPS = save._GROUPS
get_first_id = sync.get_first_id
get_last_id = sync.get_last_id
ensure_chat_access = sync.ensure_chat_access
refetch_messages = sync.refetch_messages
fetch_missing = sync.fetch_missing
remove_deleted = sync.remove_deleted


async def _heartbeat(interval: int = 60, warn_after: int = 300) -> None:
    """Periodically log a heartbeat and warn if idle for too long."""

    while True:
        await asyncio.sleep(interval)
        idle = (datetime.now(timezone.utc) - _last_event).total_seconds()
        if idle >= warn_after:
            log.warning("No updates received recently", idle=int(idle))
        else:
            log.debug("Heartbeat", idle=int(idle))


async def main(argv: list[str] | None = None) -> None:
    """Run the Telegram client CLI."""

    parser = argparse.ArgumentParser(description="Sync Telegram chats")
    parser.add_argument("--listen", action="store_true", help="stay running")
    parser.add_argument(
        "--fetch", nargs=2, metavar=("CHAT", "ID"), help="fetch one message and exit"
    )
    parser.add_argument("--ensure-access", action="store_true", help="join chats")
    parser.add_argument("--refetch", action="store_true", help="reload incomplete posts")
    parser.add_argument(
        "--fetch-missing", action="store_true", help="sync new and missing messages"
    )
    parser.add_argument("--check-deleted", action="store_true", help="purge removed")
    args = parser.parse_args(argv)

    client = TelegramClient(
        TG_SESSION,
        TG_API_ID,
        TG_API_HASH,
        sequential_updates=True,
    )
    await client.start()
    log.info("Logged in")
    global _sem
    _sem = asyncio.Semaphore(DOWNLOAD_WORKERS)
    _mark_activity()

    if args.fetch:
        chat, mid_str = args.fetch
        try:
            mid = int(mid_str)
        except ValueError:
            log.error("Invalid id", input=mid_str)
            return
        try:
            msg = await client.get_messages(chat, ids=mid)
        except Exception:
            log.exception("Failed to fetch message", chat=chat, id=mid)
            return
        if msg:
            await save._save_bounded(client, chat, msg, force_media=True)
            await save._flush_chop_queue()
            text = getattr(msg, "text", None) or getattr(msg, "message", "")
            text_short = text.strip().replace("\n", " ")[:200]
            if text_short:
                log.info("Fetched message", chat=chat, id=mid, text=text_short)
        else:
            log.error("Message not found", chat=chat, id=mid)
        await save._flush_chop_queue()
        return

    if not any(
        [args.ensure_access, args.refetch, args.fetch_missing, args.check_deleted]
    ):
        args.ensure_access = args.refetch = args.fetch_missing = True

    if args.ensure_access:
        await ensure_chat_access(client)
    if args.refetch:
        await refetch_messages(client)
    if args.fetch_missing:
        await fetch_missing(client)
    if args.check_deleted:
        await remove_deleted(client, KEEP_DAYS)
    if not args.listen:
        log.info("Sync complete")
        await save._flush_chop_queue()
        return
    log.info("Initial sync complete; listening for updates")
    asyncio.create_task(_heartbeat())

    @client.on(events.Album(chats=CHATS))
    async def album_handler(event):
        chat = event.chat.username or str(event.chat_id)
        for msg in event.messages:
            await save._save_bounded(client, chat, msg)
        _mark_activity()

    @client.on(events.NewMessage(chats=CHATS))
    async def handler(event):
        if event.message.grouped_id:
            return
        chat = event.chat.username or str(event.chat_id)
        await save._save_bounded(client, chat, event.message)
        _mark_activity()

    @client.on(events.MessageEdited(chats=CHATS))
    async def edit_handler(event):
        chat = event.chat.username or str(event.chat_id)
        await save._save_bounded(client, chat, event.message)
        _mark_activity()
        log.debug("Saved edit", chat=chat, id=event.message.id)

    log.info("Client started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
