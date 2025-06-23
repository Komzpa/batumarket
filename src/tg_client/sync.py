"""High level synchronization helpers for tg_client."""

from __future__ import annotations

import asyncio
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.custom import Message
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError

from serde_utils import load_json, write_json
from post_io import read_post
from log_utils import get_logger

from . import (
    CHATS,
    RAW_DIR,
    MEDIA_DIR,
    STATE_DIR,
    BROKEN_META_FILE,
    KEEP_DAYS,
    DOWNLOAD_WORKERS,
    _sem,
    log,
)
from .save import _save_bounded, _remove_local_message

log = get_logger().bind(module=__name__)


async def _download_messages(
    client: TelegramClient,
    chat: str,
    messages: list[Message],
    label: str,
) -> int:
    """Save ``messages`` with a progress bar and return count saved."""

    import progressbar

    if not messages:
        return 0
    widgets = [
        f"{label} ",
        progressbar.Bar(marker="#", left="[", right="]"),
        " ",
        progressbar.ETA(),
    ]
    try:
        bar = progressbar.ProgressBar(max_value=len(messages), widgets=widgets)
    except TypeError as exc:
        if "max_value" in str(exc) and "maxval" in str(exc):
            bar = progressbar.ProgressBar(maxval=len(messages), widgets=widgets)
        else:
            raise
    done = 0
    tasks: list[asyncio.Task[Path | None]] = []
    bar.start()
    for msg in messages:
        tasks.append(asyncio.create_task(_save_bounded(client, chat, msg)))
        if len(tasks) >= DOWNLOAD_WORKERS:
            await asyncio.gather(*tasks)
            done += len(tasks)
            bar.update(done)
            tasks.clear()
    if tasks:
        await asyncio.gather(*tasks)
        done += len(tasks)
        bar.update(done)
    bar.finish()
    return done


async def ensure_chat_access(client: TelegramClient) -> None:
    """Join chats listed in ``CHATS`` if not already joined."""

    for chat in CHATS:
        try:
            await client(JoinChannelRequest(chat))
            log.info("Joined chat", chat=chat)
        except UserAlreadyParticipantError:
            log.debug("Already joined", chat=chat)
        except Exception:
            log.exception("Failed to join chat", chat=chat)


async def refetch_messages(client: TelegramClient) -> None:
    """Re-fetch posts that failed parsing or are empty."""

    targets: dict[tuple[str, int], Path | None] = {}
    broken_list: list[dict] = []

    if BROKEN_META_FILE.exists():
        broken = load_json(BROKEN_META_FILE)
        if isinstance(broken, list):
            for item in broken:
                chat = item.get("chat")
                mid = item.get("id")
                if not chat or not mid:
                    continue
                key = (chat, int(mid))
                targets.setdefault(key, get_message_path(chat, int(mid)))
                broken_list.append({"chat": chat, "id": mid})

    for path in RAW_DIR.rglob("*.md"):
        meta, text = read_post(path)
        try:
            files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
        except Exception:
            files = []
        if text.strip() or files:
            continue
        chat = meta.get("chat")
        mid = meta.get("id")
        if not chat or not mid:
            continue
        key = (chat, int(mid))
        targets.setdefault(key, path)

    if not targets:
        return

    remaining_broken: list[dict] = []
    for (chat, mid), old in targets.items():
        try:
            msg = await client.get_messages(chat, ids=mid)
        except Exception:
            log.exception("Failed to refetch", chat=chat, id=mid)
            if {"chat": chat, "id": mid} in broken_list:
                remaining_broken.append({"chat": chat, "id": mid})
            continue
        if not msg:
            _remove_local_message(old)
            continue
        new_path = await _save_bounded(client, chat, msg, replace=True, old_path=old)
        if new_path is None:
            _remove_local_message(old)

    if remaining_broken:
        write_json(BROKEN_META_FILE, remaining_broken)
    elif BROKEN_META_FILE.exists():
        BROKEN_META_FILE.unlink()


def get_message_path(chat: str, msg_id: int) -> Path | None:
    for p in (RAW_DIR / chat).rglob(f"{msg_id}.md"):
        return p
    return None


def _get_id_date(chat: str, msg_id: int) -> datetime | None:
    path = get_message_path(chat, msg_id)
    if not path:
        return None
    for line in path.read_text().splitlines():
        if line.startswith("date: "):
            try:
                ts = datetime.fromisoformat(line[6:])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts
            except ValueError:
                return None
    return None


def _load_progress(chat: str) -> datetime | None:
    path = STATE_DIR / f"{chat}.txt"
    if not path.exists():
        return None
    try:
        ts = datetime.fromisoformat(path.read_text().strip())
    except ValueError:
        log.warning("Invalid progress file", path=str(path))
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _save_progress(chat: str, ts: datetime) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{chat}.txt"
    path.write_text(ts.isoformat(), encoding="utf-8")
    log.info("Saved progress", chat=chat, date=ts.isoformat(), path=str(path))


def get_first_id(chat: str) -> int:
    chat_dir = RAW_DIR / chat
    if not chat_dir.exists():
        return 0
    ids = []
    for p in chat_dir.rglob("*.md"):
        try:
            ids.append(int(p.stem))
        except ValueError:
            log.debug("Ignoring file", file=str(p))
    return min(ids) if ids else 0


def get_last_id(chat: str) -> int:
    chat_dir = RAW_DIR / chat
    if not chat_dir.exists():
        return 0
    ids = []
    for p in chat_dir.rglob("*.md"):
        try:
            ids.append(int(p.stem))
        except ValueError:
            log.debug("Ignoring file", file=str(p))
    return max(ids) if ids else 0


async def fetch_missing(client: TelegramClient) -> None:
    """Pull new messages and back-fill history until fully synced."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    now = datetime.now(timezone.utc)
    for chat in CHATS:
        progress = _load_progress(chat)
        if progress and progress < cutoff:
            log.info("Ignoring stale progress", chat=chat, date=progress.isoformat())
            progress = None
        last_id = get_last_id(chat)
        first_id = get_first_id(chat)
        last_date = _get_id_date(chat, last_id) if last_id else None
        first_date = _get_id_date(chat, first_id) if first_id else None

        if first_date is None or first_date > cutoff:
            start_date = progress or cutoff
            end_date = first_date or now
            backfill: list[Message] = []
            async for msg in client.iter_messages(
                chat, offset_date=start_date, reverse=True
            ):
                if msg.date >= end_date:
                    break
                path = (
                    RAW_DIR
                    / chat
                    / f"{msg.date:%Y}"
                    / f"{msg.date:%m}"
                    / f"{msg.id}.md"
                )
                if path.exists():
                    continue
                backfill.append(msg)
            count = await _download_messages(client, chat, backfill, f"{chat} backfill")
            log.info("Backfilled chat", chat=chat, new_messages=count)
            if end_date > start_date:
                _save_progress(chat, end_date)
            progress = end_date
            last_id = get_last_id(chat)
            last_date = _get_id_date(chat, last_id) if last_id else None
        start_date = progress or last_date or cutoff
        end_date = now
        to_fetch: list[Message] = []
        async for msg in client.iter_messages(chat, min_id=last_id, reverse=True):
            if msg.date < start_date:
                continue
            if msg.date >= end_date:
                break
            path = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
            if path.exists():
                continue
            to_fetch.append(msg)
        count = await _download_messages(client, chat, to_fetch, f"{chat} new")
        log.info("Synced chat", chat=chat, new_messages=count)
        if end_date > start_date:
            _save_progress(chat, end_date)


async def remove_deleted(client: TelegramClient, keep_days: int) -> None:
    """Delete locally stored messages removed from Telegram recently."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for chat in CHATS:
        count = 0
        for path in (RAW_DIR / chat).rglob("*.md"):
            meta, _ = read_post(path)
            date_str = meta.get("date")
            try:
                ts = datetime.fromisoformat(date_str) if date_str else None
            except ValueError:
                ts = None
            if not ts or ts < cutoff:
                continue
            try:
                msg_id = int(meta.get("id", 0))
            except (ValueError, TypeError):
                continue
            try:
                msg = await client.get_messages(chat, ids=msg_id)
            except Exception:
                log.exception("Failed to fetch message", chat=chat, id=msg_id)
                continue
            if not msg or (
                not getattr(msg, "message", None) and not getattr(msg, "media", None)
            ):
                files = []
                try:
                    files = ast.literal_eval(meta.get("files", "[]"))
                except Exception:
                    log.warning("Invalid file list", path=str(path))
                for f in files:
                    fpath = MEDIA_DIR / f
                    for extra in [
                        fpath,
                        fpath.with_suffix(".caption.md"),
                        fpath.with_suffix(".md"),
                    ]:
                        if extra.exists():
                            extra.unlink()
                            log.info("Deleted media", file=str(extra))
                path.unlink()
                count += 1
                log.info("Deleted message", chat=chat, id=msg_id)
        if count:
            log.info("Removed deleted", chat=chat, count=count)
