# Functions related to saving messages and media.

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import time
import json
import ast
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon.tl.custom import Message
from telethon import TelegramClient

from log_utils import get_logger
from serde_utils import write_json
from phone_utils import format_georgian
from post_io import write_post, read_post, get_contact
from image_io import write_image_meta
from moderation import should_skip_user, should_skip_message

from . import (
    RAW_DIR,
    MEDIA_DIR,
    LOTS_DIR,
    BROKEN_META_FILE,
    CHOP_COOLDOWN,
    CHOP_CHECK_INTERVAL,
    PROGRESS_INTERVAL,
    DOWNLOAD_TIMEOUT,
    TOPICS,
    _sem,
    _mark_activity,
    log,
)
from .helpers import (progress_logger as _progress_logger, write_md as _write_md, scan_group_cache, find_group_path, get_message_path, _GROUPS, _GROUP_CACHE)
from .queue import (
    schedule_caption as _schedule_caption,
    schedule_chop as _schedule_chop,
    enqueue_chop as _enqueue_chop,
    start_worker as _start_chop_worker,
    process_queue as _process_chop_queue,
    worker as _chop_worker,
    flush_queue as _flush_chop_queue,
)

# Queue of posts waiting for chopping. Each entry maps the message path
# to a dict with ``timestamp`` and ``pending`` fields tracking files that
# still need captions.




def _should_skip_media(msg: Message) -> str | None:
    """Return reason string if ``msg`` media should be skipped."""

    file = getattr(msg, "file", None)
    if not file:
        return None

    ext = (getattr(file, "ext", "") or "").lower()
    mtype = (getattr(file, "mime_type", "") or "").lower()
    size = getattr(file, "size", 0) or 0

    if ext == ".mp4" or mtype.startswith("video/"):
        return "video"
    if (
        ext in {".mp3", ".wav", ".ogg", ".m4a"}
        or mtype.startswith("audio/")
        or getattr(msg, "voice", False)
    ):
        return "audio"
    if mtype.startswith("image/") and size > 10 * 1024 * 1024:
        return "image-too-large"
    return None


def _allowed_topic(chat: str, msg: Message) -> bool:
    """Return ``True`` if ``msg`` belongs to an allowed forum topic."""

    allowed = TOPICS.get(chat)
    if not allowed:
        return True
    topic_id = None
    rep = getattr(msg, "reply_to", None)
    if rep and getattr(rep, "forum_topic", False):
        topic_id = getattr(rep, "reply_to_top_id", None)
    action = getattr(msg, "action", None)
    if (
        topic_id is None
        and action
        and type(action).__name__ == "MessageActionTopicCreate"
    ):
        topic_id = msg.id
    if topic_id is None:
        return False
    try:
        topic_id = int(topic_id)
    except (TypeError, ValueError):
        return False
    return topic_id in allowed


async def _extract_author(msg: Message, client: TelegramClient) -> dict:
    """Return a metadata dictionary describing the message author."""

    meta: dict[str, object] = {}

    try:
        sender = await msg.get_sender()
    except Exception:
        sender = None
        log.debug("Failed to hydrate sender", id=msg.id)

    name = (
        " ".join(
            p
            for p in [
                getattr(sender, "first_name", None),
                getattr(sender, "last_name", None),
            ]
            if p
        )
        or None
    )
    meta["sender"] = getattr(sender, "id", None)
    meta["sender_username"] = getattr(sender, "username", None)
    meta["sender_phone"] = format_georgian(getattr(sender, "phone", "") or "")
    meta["tg_link"] = (
        f"https://t.me/{sender.username}" if getattr(sender, "username", None) else None
    )
    meta["sender_name"] = name or getattr(msg, "post_author", None)
    meta["post_author"] = getattr(msg, "post_author", None)

    if getattr(sender, "id", None):
        meta["author_type"] = "user"
    elif getattr(msg, "sender_chat", None):
        chat_ent = getattr(msg, "sender_chat")
        if not getattr(chat_ent, "title", None):
            try:
                chat_ent = await client.get_entity(chat_ent)
            except Exception:
                chat_ent = None
                log.debug("Failed to hydrate sender_chat", id=msg.id)
        meta["sender"] = None
        meta["sender_chat"] = getattr(chat_ent, "id", None)
        meta["sender_chat_title"] = getattr(chat_ent, "title", None)
        meta["post_author"] = getattr(msg, "post_author", None)
        meta["author_type"] = "channel"
        if meta.get("sender_name") is None:
            meta["sender_name"] = getattr(msg, "post_author", None)
    elif getattr(msg, "fwd_from", None):
        fwd = msg.fwd_from
        meta["author_type"] = "forward"
        meta["fwd_from_id"] = getattr(getattr(fwd, "from_id", None), "user_id", None)
        meta["fwd_from_name"] = getattr(fwd, "from_name", None)
        meta["sender"] = None
        if meta.get("sender_name") is None:
            meta["sender_name"] = getattr(msg, "post_author", None)
        meta["post_author"] = getattr(msg, "post_author", None)
    else:
        meta["author_type"] = "service"
        meta["sender"] = None
        if meta.get("sender_name") is None:
            meta["sender_name"] = getattr(msg, "post_author", None)
        meta["post_author"] = getattr(msg, "post_author", None)

    return meta

async def _save_message(
    client: TelegramClient,
    chat: str,
    msg: Message,
    *,
    replace: bool = False,
    old_path: Path | None = None,
    force_media: bool = False,
) -> Path | None:
    """Write ``msg`` to disk with metadata and any media references.

    Returns the path of the stored message or ``None`` when skipped."""

    _mark_activity()
    log.debug("Processing message", chat=chat, id=msg.id)
    if not _allowed_topic(chat, msg):
        log.debug("Skipping topic", chat=chat, id=msg.id)
        return None
    author = await _extract_author(msg, client)
    username = author.get("sender_username")
    if should_skip_user(username):
        log.debug(
            "Skipping blacklisted user",
            chat=chat,
            id=msg.id,
            user=username,
        )
        return None
    subdir = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    group_path = (
        _GROUPS.get(msg.grouped_id) or find_group_path(chat, msg.grouped_id)
        if msg.grouped_id
        else None
    )
    path = old_path or group_path or subdir / f"{msg.id}.md"

    meta_prev: dict[str, object] = {}
    body_prev = ""
    files_prev: list[str] = []
    if path.exists() and not replace:
        meta_prev, body_prev = read_post(path)
        try:
            files_prev = (
                ast.literal_eval(meta_prev.get("files", "[]"))
                if "files" in meta_prev
                else []
            )
        except Exception:
            log.warning("Invalid file list", path=str(path))
        if force_media:
            meta_prev.pop("skipped_media", None)

    files = []
    skipped_reason = None
    if msg.media:
        reason = None if force_media else _should_skip_media(msg)
        if reason:
            log.info("Skipping media", chat=chat, id=msg.id, reason=reason)
        if reason and not files_prev:
            skipped_reason = reason
        if reason is None:
            if files_prev:
                log.debug(
                    "Keeping existing media",
                    chat=chat,
                    id=msg.id,
                    files=len(files_prev),
                )
            else:
                log.debug("Downloading media", chat=chat, id=msg.id)
                try:
                    data = await asyncio.wait_for(
                        msg.download_media(
                            bytes, progress_callback=_progress_logger(chat, msg.id)
                        ),
                        timeout=DOWNLOAD_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    log.error("Media download timed out", chat=chat, id=msg.id)
                    data = None
                    skipped_reason = "timeout"
                if isinstance(data, (bytes, bytearray)):
                    files.append(await _save_media(chat, msg, data))
                else:
                    if data is not None:
                        log.warning("Cannot download media", chat=chat, id=msg.id)
                    if skipped_reason is None:
                        skipped_reason = "download"

    permissions = None
    try:
        permissions = await client.get_permissions(chat, msg.sender_id)
    except Exception:
        log.debug("Failed to fetch permissions", chat=chat, user=msg.sender_id)

    sender_id = author.get("sender")
    sender_name = author.get("sender_name")
    if sender_id is None and "sender_chat" not in author:
        log.warning("Message sender missing", chat=chat, id=msg.id)

    meta = {
        "id": msg.id,
        "chat": chat,
        **author,
        "sender": sender_id,
        "sender_name": sender_name,
        "date": msg.date.isoformat(),
        "reply_to": msg.reply_to_msg_id,
        "group_id": msg.grouped_id,
        "is_admin": getattr(permissions, "is_admin", False),
    }
    if files:
        meta["files"] = files
    if skipped_reason and not force_media:
        meta["skipped_media"] = skipped_reason

    text = (
        getattr(msg, "text", None)
        or getattr(getattr(msg, "media", None), "caption", None)
        or getattr(msg, "message", "")
    )
    log.debug("Raw message text", chat=chat, id=msg.id, preview=str(text)[:80])
    text = str(text).replace("View original post", "").strip()
    log.debug("Processed message text", chat=chat, id=msg.id, preview=text[:80])
    log.debug(
        "Saving message",
        chat=chat,
        id=msg.id,
        files=len(files_prev) + len(files),
        preview=text[:80],
    )
    if meta_prev and not replace:
        files = list(dict.fromkeys(files_prev + files))
        meta_prev.update(meta)
        meta_prev["files"] = files
        meta = meta_prev
        text = body_prev or text

    if get_contact(meta) is None:
        preview = text.replace("\n", " ")[:120]
        log.warning(
            "Missing contact",
            chat=chat,
            id=msg.id,
            preview=preview,
            meta=json.dumps(meta, ensure_ascii=False),
        )
        return None
    if replace and old_path and old_path != path and old_path.exists():
        old_path.unlink()
        lot_old = LOTS_DIR / old_path.relative_to(RAW_DIR).with_suffix(".json")
        if lot_old.exists():
            lot_old.unlink()
            log.info("Dropped lots after refetch", file=str(lot_old))
    if replace and path.exists():
        path.unlink()
    for key in ["id", "chat", "date"]:
        assert meta.get(key) not in (None, ""), f"missing {key}"
    if meta.get("sender") in (None, ""):
        log.debug("Sender id unavailable", chat=chat, id=msg.id)
    if "files" in meta:
        meta["files"] = list(dict.fromkeys(meta["files"]))
        assert len(meta["files"]) == len(set(meta["files"])), "duplicate files"
    _write_md(path, meta, text)

    if replace:
        lot_path = LOTS_DIR / path.relative_to(RAW_DIR).with_suffix(".json")
        if lot_path.exists():
            lot_path.unlink()
            log.info("Dropped lots after refetch", file=str(lot_path))

    if msg.grouped_id:
        _GROUP_CACHE.setdefault(chat, {})[msg.grouped_id] = path
        _GROUPS[msg.grouped_id] = path

    if msg.grouped_id and not replace and group_path is None:
        try:
            start = max(1, msg.id - 9)
            end = msg.id + 9
            ids = list(range(start, end + 1))
            others = await client.get_messages(chat, ids=ids)
            for other in others:
                if other.id == msg.id:
                    continue
                if getattr(other, "grouped_id", None) == msg.grouped_id:
                    await _save_message(client, chat, other)
        except Exception:
            log.exception("Failed to fetch album", chat=chat, id=msg.id)

    log.info("Wrote message", path=str(path), id=msg.id)
    _enqueue_chop(path, meta, text)
    return path


async def _save_media(chat: str, msg: Message, data: bytes) -> str:
    """Store ``data`` and return relative file path."""

    sha = hashlib.sha256(data).hexdigest()
    ext = getattr(msg.file, "ext", "") or ""
    subdir = MEDIA_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    filename = f"{sha}{ext}"
    path = subdir / filename
    caption = path.with_suffix(".caption.md")
    if not path.exists():
        path.write_bytes(data)
        log.info(
            "Stored media",
            sha=sha,
            bytes=len(data),
            path=str(path),
        )
    else:
        log.debug("Media exists", sha=sha, path=str(path))

    mime = (getattr(msg.file, "mime_type", "") or "").lower()
    if mime.startswith("image/"):
        if not caption.exists():
            _schedule_caption(path)
        else:
            log.debug("Caption exists", file=str(caption))
    meta = {
        "message_id": msg.id,
        "date": msg.date.isoformat(),
        "original": getattr(msg.file, "name", None),
    }
    write_image_meta(path, meta)
    rel = Path(chat) / f"{msg.date:%Y}" / f"{msg.date:%m}" / filename
    return str(rel)


async def _save_bounded(
    client: TelegramClient,
    chat: str,
    msg: Message,
    *,
    replace: bool = False,
    old_path: Path | None = None,
    force_media: bool = False,
) -> Path | None:
    """Run ``_save_message`` under the global semaphore and return path."""

    assert _sem is not None
    async with _sem:
        return await _save_message(
            client,
            chat,
            msg,
            replace=replace,
            old_path=old_path,
            force_media=force_media,
        )


def _remove_local_message(path: Path | None) -> None:
    """Delete ``path`` and related media if the post no longer exists."""

    if not path or not path.exists():
        return
    meta, _ = read_post(path)
    files: list[str] = []
    try:
        files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
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
    lot = LOTS_DIR / path.relative_to(RAW_DIR).with_suffix(".json")
    if lot.exists():
        lot.unlink()
        log.info("Dropped lots", file=str(lot))
    path.unlink()
    log.info("Deleted raw post", file=str(path))
