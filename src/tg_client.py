"""Mirror Telegram chats using a user account via Telethon."""

import argparse
import asyncio
import hashlib
import ast
import subprocess
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
import progressbar
from telethon.tl.custom import Message
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError
from notes_utils import load_json, write_json
from log_utils import get_logger, install_excepthook
from oom_utils import prefer_oom_kill
from post_io import raw_post_path
from caption_io import (
    has_caption,
    caption_json_path,
    caption_md_path,
)

# Log progress on long downloads every few seconds and abort if they
# run for too long.
PROGRESS_INTERVAL = 5  # seconds between progress messages
DOWNLOAD_TIMEOUT = 300  # maximum seconds to spend downloading a file


# Timestamp of the last successfully processed update or message.  Used by
# the heartbeat coroutine to detect hangs.
_last_event = datetime.now(timezone.utc)

# Semaphore limiting concurrent downloads.
_sem: asyncio.Semaphore


def _mark_activity() -> None:
    """Update ``_last_event`` to the current time."""
    global _last_event
    _last_event = datetime.now(timezone.utc)


from config_utils import load_config

log = get_logger().bind(script=__file__)
install_excepthook(log)
prefer_oom_kill()

cfg = load_config()
TG_API_ID = cfg.TG_API_ID
TG_API_HASH = cfg.TG_API_HASH
TG_SESSION = cfg.TG_SESSION
KEEP_DAYS = getattr(cfg, "KEEP_DAYS", 7)
DOWNLOAD_WORKERS = getattr(cfg, "DOWNLOAD_WORKERS", 4)

# Parse chat list extracting optional ``chat/topic`` entries.  ``CHATS`` holds
# unique chat names while ``TOPICS`` maps chats to allowed forum topic IDs.  A
# plain chat name disables any topic filters for that chat.
TOPICS: dict[str, list[int]] = {}
_chats: list[str] = []
for item in cfg.CHATS:
    if "/" in item:
        chat, tid_str = item.split("/", 1)
        if chat in TOPICS and TOPICS[chat] is None:
            # Full chat already requested
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
_sem = asyncio.Semaphore(DOWNLOAD_WORKERS)
from phone_utils import format_georgian
from post_io import write_post, read_post, get_contact
from image_io import write_image_meta
from moderation import should_skip_user, should_skip_message


async def _heartbeat(interval: int = 60, warn_after: int = 300) -> None:
    """Periodically log a heartbeat and warn if idle for too long."""
    while True:
        await asyncio.sleep(interval)
        idle = (datetime.now(timezone.utc) - _last_event).total_seconds()
        if idle >= warn_after:
            log.warning("No updates received recently", idle=int(idle))
        else:
            log.debug("Heartbeat", idle=int(idle))


# Messages are stored as Markdown with metadata under
# data/raw/<chat>/<YYYY>/<MM>/<id>.md.  Media files live under
# data/media/<chat>/<YYYY>/<MM>/ using their SHA-256 hash plus extension.
RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")
STATE_DIR = Path("data/state")
# List of message ids that should be re-fetched due to missing metadata.
BROKEN_META_FILE = Path("data/ontology/broken_meta.json")
LOTS_DIR = Path("data/lots")

# Seconds to wait before chopping a freshly saved message.  This gives
# albums enough time to arrive in multiple updates and avoids chopping
# partial posts.
CHOP_COOLDOWN = int(os.getenv("CHOP_COOLDOWN", "20"))
# How often to check the queue for cooled down messages.
CHOP_CHECK_INTERVAL = 5
# Maximum seconds to wait for the chop queue to drain when exiting.
CHOP_FLUSH_TIMEOUT = int(os.getenv("CHOP_FLUSH_TIMEOUT", "60"))

# Queue of posts waiting for chopping.  Each entry maps the message path
# to a dict with ``timestamp`` and ``pending`` fields tracking files that
# still need captions.
_CHOP_QUEUE: dict[Path, dict[str, object]] = {}
_chop_task: asyncio.Task | None = None


def _progress_logger(chat: str, msg_id: int):
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


def _write_md(path: Path, meta: dict, body: str) -> None:
    """Helper to store a raw post in Markdown format."""
    write_post(path, meta, body)


_GROUPS: dict[int, Path] = {}
# Cache of group_id -> Path for previously stored messages, keyed by chat.
_GROUP_CACHE: dict[str, dict[int, Path]] = {}


def _scan_group_cache(chat: str) -> dict[int, Path]:
    """Build group_id -> Path mapping for ``chat`` quickly."""
    chat_dir = raw_post_path(chat, RAW_DIR)
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


def _find_group_path(chat: str, group_id: int) -> Path | None:
    """Return stored message path for ``group_id`` if known."""
    groups = _GROUP_CACHE.get(chat)
    if groups is None:
        groups = _scan_group_cache(chat)
        _GROUP_CACHE[chat] = groups
    return groups.get(group_id)


def _get_message_path(chat: str, msg_id: int) -> Path | None:
    """Return path of stored message ``msg_id`` in ``chat`` if any."""
    for p in raw_post_path(chat, RAW_DIR).rglob(f"{msg_id}.md"):
        return p
    return None


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


def _schedule_caption(path: Path) -> None:
    """Run captioning in a separate process so downloads continue."""
    try:
        subprocess.Popen([sys.executable, "src/caption.py", str(path)])
        log.debug("Caption scheduled", file=str(path))
    except Exception:
        log.exception("Failed to schedule caption", file=str(path))


def _schedule_chop(msg_path: Path) -> None:
    """Run lot extraction in a separate process."""
    if os.getenv("TEST_MODE") == "1":
        log.debug("Skip chop in test mode", file=str(msg_path))
        return
    try:
        subprocess.Popen([sys.executable, "src/chop.py", str(msg_path)])
        log.debug("Chop scheduled", file=str(msg_path))
    except Exception:
        log.exception("Failed to schedule chop", file=str(msg_path))


def _enqueue_chop(path: Path, meta: dict, text: str) -> None:
    """Queue ``path`` for chopping once captions are available."""
    if should_skip_message(meta, text):
        log.debug("Skipping chop due to moderation", path=str(path))
        return
    files = meta.get("files", [])
    pending: set[Path] = set()
    for rel in files:
        p = MEDIA_DIR / rel
        if p.suffix.lower().startswith(".jpg") or p.suffix.lower() in {
            ".png",
            ".gif",
            ".webp",
        }:
            if not has_caption(p):
                pending.add(p)
    entry = _CHOP_QUEUE.get(path)
    if entry:
        entry["pending"].update(pending)
        entry["timestamp"] = time.monotonic()
    else:
        _CHOP_QUEUE[path] = {"timestamp": time.monotonic(), "pending": pending}
    log.debug(
        "Queued chop",
        file=str(path),
        pending=len(pending),
        queue=len(_CHOP_QUEUE),
    )
    _start_chop_worker()


def _start_chop_worker() -> None:
    """Ensure the chop queue worker task is running."""
    global _chop_task
    if _chop_task is None or _chop_task.done():
        log.debug("Starting chop worker", queue=len(_CHOP_QUEUE))
        _chop_task = asyncio.create_task(_chop_worker())


def _process_chop_queue() -> None:
    """Check queued posts and chop cooled down ones."""
    now = time.monotonic()
    for path, item in list(_CHOP_QUEUE.items()):
        pending = {p for p in item["pending"] if not has_caption(p)}
        item["pending"] = pending
        if not pending and now - item["timestamp"] >= CHOP_COOLDOWN:
            log.debug("Chop cooldown complete", file=str(path))
            _schedule_chop(path)
            del _CHOP_QUEUE[path]


async def _chop_worker() -> None:
    """Background task processing ``_CHOP_QUEUE``."""
    while _CHOP_QUEUE:
        log.debug("Chop worker tick", queue=len(_CHOP_QUEUE))
        _process_chop_queue()
        if not _CHOP_QUEUE:
            break
        await asyncio.sleep(CHOP_CHECK_INTERVAL)


async def _flush_chop_queue() -> None:
    """Run the chop worker until the queue is empty and cancel it."""
    global _chop_task
    if _chop_task is None:
        return
    log.debug("Flushing chop queue", queue=len(_CHOP_QUEUE))
    start = time.monotonic()
    while _CHOP_QUEUE and time.monotonic() - start < CHOP_FLUSH_TIMEOUT:
        _process_chop_queue()
        if not _CHOP_QUEUE:
            break
        await asyncio.sleep(CHOP_CHECK_INTERVAL)
    if _CHOP_QUEUE:
        paths = [str(p) for p in _CHOP_QUEUE.keys()]
        log.warning("Chop queue not empty", pending=len(paths), paths=paths)
    if _chop_task:
        _chop_task.cancel()
        try:
            await _chop_task
        except asyncio.CancelledError:
            pass
        _chop_task = None


def _get_id_date(chat: str, msg_id: int) -> datetime | None:
    """Return the stored date for ``msg_id`` in ``chat`` if available."""
    path = None
    for p in raw_post_path(chat, RAW_DIR).rglob(f"{msg_id}.md"):
        path = p
        break
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
    """Return saved resume timestamp for ``chat`` if available."""
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
    """Persist resume timestamp for ``chat`` to ``STATE_DIR``."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{chat}.txt"
    path.write_text(ts.isoformat(), encoding="utf-8")
    log.info("Saved progress", chat=chat, date=ts.isoformat(), path=str(path))


def get_first_id(chat: str) -> int:
    """Return the smallest saved message id for ``chat``."""
    chat_dir = raw_post_path(chat, RAW_DIR)
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
    """Return the highest saved message id for ``chat``."""
    chat_dir = raw_post_path(chat, RAW_DIR)
    if not chat_dir.exists():
        return 0
    ids = []
    for p in chat_dir.rglob("*.md"):
        try:
            ids.append(int(p.stem))
        except ValueError:
            log.debug("Ignoring file", file=str(p))
    return max(ids) if ids else 0


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
    rel = Path(chat) / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
    group_path = (
        _GROUPS.get(msg.grouped_id) or _find_group_path(chat, msg.grouped_id)
        if msg.grouped_id
        else None
    )
    path = old_path or group_path or raw_post_path(rel, RAW_DIR)
    path.parent.mkdir(parents=True, exist_ok=True)

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
    # Files are grouped by chat and month so we don't end up with one huge
    # directory.  A companion ``.md`` file holds basic metadata about the
    # original file and source message.
    sha = hashlib.sha256(data).hexdigest()
    ext = getattr(msg.file, "ext", "") or ""
    subdir = MEDIA_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    filename = f"{sha}{ext}"
    path = subdir / filename
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
        if not has_caption(path):
            _schedule_caption(path)
        else:
            log.debug("Caption exists", file=str(caption_json_path(path)))
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
        for extra in [fpath, caption_json_path(fpath), caption_md_path(fpath), fpath.with_suffix(".md")]:
            if extra.exists():
                extra.unlink()
                log.info("Deleted media", file=str(extra))
    lot = LOTS_DIR / path.relative_to(RAW_DIR).with_suffix(".json")
    if lot.exists():
        lot.unlink()
        log.info("Dropped lots", file=str(lot))
    path.unlink()
    log.info("Deleted raw post", file=str(path))


async def _download_messages(
    client: TelegramClient,
    chat: str,
    messages: list[Message],
    label: str,
) -> int:
    """Save ``messages`` with a progress bar and return count saved."""
    if not messages:
        return 0
    widgets = [
        f"{label} ",
        progressbar.Bar(marker="#", left="[", right="]"),
        " ",
        progressbar.ETA(),
    ]
    # progressbar2 uses ``max_value`` while the older ``progressbar`` package
    # expects ``maxval``.  The fallback keeps compatibility when only the legacy
    # module is installed.
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
                targets.setdefault(key, _get_message_path(chat, int(mid)))
                broken_list.append({"chat": chat, "id": mid})

    for path in raw_post_path(Path(), RAW_DIR).rglob("*.md"):
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


async def fetch_missing(client: TelegramClient) -> None:
    """Pull new messages and back-fill history until fully synced."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    now = datetime.now(timezone.utc)
    for chat in CHATS:
        progress = _load_progress(chat)
        # When KEEP_DAYS gets lowered old state files may point to timestamps
        # far in the past.  Dropping those prevents re-fetching messages that
        # were intentionally cleaned up.
        if progress and progress < cutoff:
            log.info("Ignoring stale progress", chat=chat, date=progress.isoformat())
            progress = None
        last_id = get_last_id(chat)
        first_id = get_first_id(chat)
        last_date = _get_id_date(chat, last_id) if last_id else None
        first_date = _get_id_date(chat, first_id) if first_id else None

        # Decide whether to fetch newer or older messages.
        if first_date is None or first_date > cutoff:
            start_date = progress or cutoff
            end_date = first_date or now
            backfill: list[Message] = []
            try:
                async for msg in client.iter_messages(
                    chat, offset_date=start_date, reverse=True
                ):
                    if msg.date >= end_date:
                        break
                    rel = (
                        Path(chat)
                        / f"{msg.date:%Y}"
                        / f"{msg.date:%m}"
                        / f"{msg.id}.md"
                    )
                    path = raw_post_path(rel, RAW_DIR)
                    if path.exists():
                        continue
                    backfill.append(msg)
            except ValueError as exc:
                if "username" in str(exc):
                    log.warning("Skipping invalid chat", chat=chat)
                    continue
                raise
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
        try:
            async for msg in client.iter_messages(chat, min_id=last_id, reverse=True):
                if msg.date < start_date:
                    continue
                if msg.date >= end_date:
                    break
                rel = Path(chat) / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
                path = raw_post_path(rel, RAW_DIR)
                if path.exists():
                    continue
                to_fetch.append(msg)
        except ValueError as exc:
            if "username" in str(exc):
                log.warning("Skipping invalid chat", chat=chat)
                continue
            raise
        count = await _download_messages(client, chat, to_fetch, f"{chat} new")
        log.info("Synced chat", chat=chat, new_messages=count)
        if end_date > start_date:
            _save_progress(chat, end_date)


async def remove_deleted(client: TelegramClient, keep_days: int) -> None:
    """Delete locally stored messages removed from Telegram recently."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for chat in CHATS:
        count = 0
        for path in raw_post_path(chat, RAW_DIR).rglob("*.md"):
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
                        caption_json_path(fpath),
                        caption_md_path(fpath),
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


async def main(argv: list[str] | None = None) -> None:
    """Synchronize configured chats and optional live updates."""
    parser = argparse.ArgumentParser(description="Sync Telegram chats")
    parser.add_argument(
        "--listen",
        action="store_true",
        help="stay running and process new updates",
    )
    parser.add_argument(
        "--fetch",
        nargs=2,
        metavar=("CHAT", "ID"),
        help="download a single message for investigation and exit",
    )
    parser.add_argument(
        "--ensure-access",
        action="store_true",
        help="join configured chats and exit",
    )
    parser.add_argument(
        "--refetch",
        action="store_true",
        help="reload messages missing metadata or content and exit",
    )
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="sync new and backfill missing messages",
    )
    parser.add_argument(
        "--check-deleted",
        action="store_true",
        help="remove posts deleted from Telegram and exit",
    )
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
            await _save_bounded(client, chat, msg, force_media=True)
            await _flush_chop_queue()
            text = getattr(msg, "text", None) or getattr(msg, "message", "")
            text_short = text.strip().replace("\n", " ")[:200]
            if text_short:
                log.info("Fetched message", chat=chat, id=mid, text=text_short)
        else:
            log.error("Message not found", chat=chat, id=mid)
        await _flush_chop_queue()
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
        await _flush_chop_queue()
        return
    log.info("Initial sync complete; listening for updates")
    asyncio.create_task(_heartbeat())

    @client.on(events.Album(chats=CHATS))
    async def album_handler(event):
        chat = event.chat.username or str(event.chat_id)
        for msg in event.messages:
            await _save_bounded(client, chat, msg)
        _mark_activity()

    @client.on(events.NewMessage(chats=CHATS))
    async def handler(event):
        if event.message.grouped_id:
            return
        chat = event.chat.username or str(event.chat_id)
        await _save_bounded(client, chat, event.message)
        _mark_activity()

    @client.on(events.MessageEdited(chats=CHATS))
    async def edit_handler(event):
        chat = event.chat.username or str(event.chat_id)
        await _save_bounded(client, chat, event.message)
        _mark_activity()
        log.debug("Saved edit", chat=chat, id=event.message.id)

    log.info("Client started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
