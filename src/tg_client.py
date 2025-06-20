"""Mirror Telegram chats using a user account via Telethon."""

import argparse
import asyncio
import hashlib
import ast
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
from telethon.tl.custom import Message
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError

# Log progress on long downloads every few seconds and abort if they
# run for too long.
PROGRESS_INTERVAL = 5  # seconds between progress messages
DOWNLOAD_TIMEOUT = 300  # maximum seconds to spend downloading a file

# Media older than this won't be downloaded.  Skipping saves bandwidth while
# allowing the text of old posts to be archived.
MEDIA_MAX_AGE = timedelta(days=2)

# Timestamp of the last successfully processed update or message.  Used by
# the heartbeat coroutine to detect hangs.
_last_event = datetime.now(timezone.utc)


def _mark_activity() -> None:
    """Update ``_last_event`` to the current time."""
    global _last_event
    _last_event = datetime.now(timezone.utc)


from config_utils import load_config

cfg = load_config()
TG_API_ID = cfg.TG_API_ID
TG_API_HASH = cfg.TG_API_HASH
TG_SESSION = cfg.TG_SESSION
CHATS = cfg.CHATS
KEEP_DAYS = getattr(cfg, "KEEP_DAYS", 7)
from log_utils import get_logger, install_excepthook
from phone_utils import format_georgian
from notes_utils import write_md

log = get_logger().bind(script=__file__)
install_excepthook(log)


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


def _parse_md(path: Path) -> tuple[dict, str]:
    """Return metadata dict and message text from ``path``."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    meta = {}
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = "\n".join(lines[body_start:])
    return meta, body


def _write_md(path: Path, meta: dict, body: str) -> None:
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    write_md(path, "\n".join(meta_lines) + "\n\n" + body.strip())


_GROUPS: dict[int, Path] = {}


def _find_group_path(chat: str, group_id: int) -> Path | None:
    """Search stored messages for ``group_id`` to keep albums together."""
    for p in (RAW_DIR / chat).rglob("*.md"):
        meta, _ = _parse_md(p)
        try:
            if int(meta.get("group_id", 0)) == group_id:
                return p
        except (ValueError, TypeError):
            continue
    return None


def _should_skip_media(msg: Message) -> str | None:
    """Return reason string if ``msg`` media should be skipped."""
    file = getattr(msg, "file", None)
    if not file:
        return None

    msg_date = getattr(msg, "date", None)
    if isinstance(msg_date, datetime):
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - msg_date > MEDIA_MAX_AGE:
            return "old"

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


def _schedule_caption(path: Path) -> None:
    """Run captioning in a separate process so downloads continue."""
    try:
        subprocess.Popen([sys.executable, "src/caption.py", str(path)])
        log.debug("Caption scheduled", file=str(path))
    except Exception:
        log.exception("Failed to schedule caption", file=str(path))


def _get_id_date(chat: str, msg_id: int) -> datetime | None:
    """Return the stored date for ``msg_id`` in ``chat`` if available."""
    path = None
    for p in (RAW_DIR / chat).rglob(f"{msg_id}.md"):
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
    """Return the highest saved message id for ``chat``."""
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


async def _save_message(client: TelegramClient, chat: str, msg: Message) -> None:
    """Write ``msg`` to disk with metadata and any media references."""
    _mark_activity()
    log.debug("Processing message", chat=chat, id=msg.id)
    subdir = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    files = []
    if msg.media:
        reason = _should_skip_media(msg)
        if reason:
            log.info("Skipping media", chat=chat, id=msg.id, reason=reason)
        else:
            log.debug("Downloading media", chat=chat, id=msg.id)
            try:
                data = await asyncio.wait_for(
                    msg.download_media(bytes, progress_callback=_progress_logger(chat, msg.id)),
                    timeout=DOWNLOAD_TIMEOUT,
                )
            except asyncio.TimeoutError:
                log.error("Media download timed out", chat=chat, id=msg.id)
                data = None
            if isinstance(data, (bytes, bytearray)):
                files.append(await _save_media(chat, msg, data))
            else:
                log.warning("Cannot download media", chat=chat, id=msg.id)

    permissions = None
    try:
        permissions = await client.get_permissions(chat, msg.sender_id)
    except Exception:
        log.debug("Failed to fetch permissions", chat=chat, user=msg.sender_id)

    sender = await msg.get_sender()
    post_author = getattr(msg, "post_author", None)
    sender_name = " ".join(
        p for p in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if p
    ) or None
    if not sender_name:
        sender_name = post_author

    meta = {
        "id": msg.id,
        "chat": chat,
        "sender": msg.sender_id,
        "sender_name": sender_name,
        "post_author": post_author,
        "sender_username": getattr(sender, "username", None),
        "sender_phone": format_georgian(getattr(sender, "phone", "") or ""),
        "tg_link": f"https://t.me/{sender.username}" if getattr(sender, "username", None) else None,
        "date": msg.date.isoformat(),
        "reply_to": msg.reply_to_msg_id,
        "group_id": msg.grouped_id,
        "is_admin": getattr(permissions, "is_admin", False),
    }
    if files:
        meta["files"] = files

    text = (msg.message or "").replace("View original post", "").strip()
    group_path = None
    if msg.grouped_id:
        group_path = _GROUPS.get(msg.grouped_id) or _find_group_path(chat, msg.grouped_id)
        if group_path:
            meta_prev, body_prev = _parse_md(group_path)
            files_prev = ast.literal_eval(meta_prev.get("files", "[]")) if "files" in meta_prev else []
            files = files_prev + files
            meta_prev.update(meta)
            meta_prev["files"] = files
            meta = meta_prev
            text = body_prev or text
        else:
            group_path = subdir / f"{msg.id}.md"
        _GROUPS[msg.grouped_id] = group_path
    path = group_path or subdir / f"{msg.id}.md"
    _write_md(path, meta, text)
    log.info("Wrote message", path=str(path), id=msg.id)


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
    md = subdir / f"{filename}.md"
    meta = {
        "message_id": msg.id,
        "date": msg.date.isoformat(),
        "original": getattr(msg.file, "name", None),
    }
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v]
    write_md(md, "\n".join(meta_lines))
    rel = Path(chat) / f"{msg.date:%Y}" / f"{msg.date:%m}" / filename
    return str(rel)


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


async def fetch_missing(client: TelegramClient) -> None:
    """Pull new messages and back-fill history in one-day increments."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=31)
    now = datetime.now(timezone.utc)
    for chat in CHATS:
        progress = _load_progress(chat)
        last_id = get_last_id(chat)
        first_id = get_first_id(chat)
        last_date = _get_id_date(chat, last_id) if last_id else None
        first_date = _get_id_date(chat, first_id) if first_id else None

        # Decide whether to fetch newer or older messages.
        if first_date is None or first_date > cutoff:
            start_date = progress or (cutoff if first_date is None else max(cutoff, first_date - timedelta(days=1)))
            end_date = min(first_date or now, start_date + timedelta(days=1))
            count = 0
            async for msg in client.iter_messages(chat, offset_date=start_date, reverse=True):
                if msg.date >= end_date:
                    break
                path = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
                if path.exists():
                    continue
                await _save_message(client, chat, msg)
                count += 1
            log.info("Backfilled chat", chat=chat, new_messages=count)
            if end_date > start_date:
                _save_progress(chat, end_date)
        else:
            start_date = progress or last_date or cutoff
            end_date = min(now, start_date + timedelta(days=1))
            count = 0
            async for msg in client.iter_messages(chat, min_id=last_id, reverse=True):
                if msg.date < start_date:
                    continue
                if msg.date >= end_date:
                    break
                path = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
                if path.exists():
                    continue
                await _save_message(client, chat, msg)
                count += 1
            log.info("Synced chat", chat=chat, new_messages=count)
            if end_date > start_date:
                _save_progress(chat, end_date)


async def remove_deleted(client: TelegramClient, keep_days: int) -> None:
    """Delete locally stored messages removed from Telegram recently."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for chat in CHATS:
        count = 0
        for path in (RAW_DIR / chat).rglob("*.md"):
            meta, _ = _parse_md(path)
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
            if not msg or (not getattr(msg, "message", None) and not getattr(msg, "media", None)):
                files = []
                try:
                    files = ast.literal_eval(meta.get("files", "[]"))
                except Exception:
                    log.warning("Invalid file list", path=str(path))
                for f in files:
                    fpath = MEDIA_DIR / f
                    for extra in [fpath, fpath.with_suffix(".caption.md"), fpath.with_suffix(".md")]:
                        if extra.exists():
                            extra.unlink()
                            log.info("Deleted media", file=str(extra))
                path.unlink()
                count += 1
                log.info("Deleted message", chat=chat, id=msg_id)
        if count:
            log.info("Removed deleted", chat=chat, count=count)


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sync Telegram chats")
    parser.add_argument(
        "--listen",
        action="store_true",
        help="stay running and process new updates",
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
    _mark_activity()

    await ensure_chat_access(client)

    await fetch_missing(client)
    await remove_deleted(client, KEEP_DAYS)
    if not args.listen:
        log.info("Sync complete")
        return
    log.info("Initial sync complete; listening for updates")
    asyncio.create_task(_heartbeat())

    @client.on(events.NewMessage(chats=CHATS))
    async def handler(event):
        chat = event.chat.username or str(event.chat_id)
        await _save_message(client, chat, event.message)
        _mark_activity()

    @client.on(events.MessageEdited(chats=CHATS))
    async def edit_handler(event):
        chat = event.chat.username or str(event.chat_id)
        await _save_message(client, chat, event.message)
        _mark_activity()
        log.debug("Saved edit", chat=chat, id=event.message.id)

    log.info("Client started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
