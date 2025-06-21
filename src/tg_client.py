"""Mirror Telegram chats using a user account via Telethon."""

import argparse
import asyncio
import hashlib
import ast
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
import progressbar
from telethon.tl.custom import Message
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError
from serde_utils import load_json, write_json

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

# Semaphore limiting concurrent downloads.
_sem: asyncio.Semaphore


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
DOWNLOAD_WORKERS = getattr(cfg, "DOWNLOAD_WORKERS", 4)
_sem = asyncio.Semaphore(DOWNLOAD_WORKERS)
from log_utils import get_logger, install_excepthook
from phone_utils import format_georgian
from post_io import write_post, read_post
from image_io import write_image_meta

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
# List of message ids that should be re-fetched due to missing metadata.
BROKEN_META_FILE = Path("data/ontology/broken_meta.json")
MISPARSED_FILE = Path("data/ontology/misparsed.json")
LOTS_DIR = Path("data/lots")


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


def _find_group_path(chat: str, group_id: int) -> Path | None:
    """Search stored messages for ``group_id`` to keep albums together."""
    for p in (RAW_DIR / chat).rglob("*.md"):
        meta, _ = read_post(p)
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


async def _save_message(client: TelegramClient, chat: str, msg: Message) -> Path:
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

    text = (
        getattr(msg, "text", None)
        or getattr(getattr(msg, "media", None), "caption", None)
        or getattr(msg, "message", "")
    )
    text = str(text).replace("View original post", "").strip()
    group_path = None
    if msg.grouped_id:
        group_path = _GROUPS.get(msg.grouped_id) or _find_group_path(chat, msg.grouped_id)
        if group_path:
            meta_prev, body_prev = read_post(group_path)
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
    for key in ["id", "chat", "date", "sender"]:
        assert meta.get(key) not in (None, ""), f"missing {key}"
    _write_md(path, meta, text)
    log.info("Wrote message", path=str(path), id=msg.id)
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


async def _save_bounded(client: TelegramClient, chat: str, msg: Message) -> Path:
    """Run ``_save_message`` under the global semaphore and return path."""
    assert _sem is not None
    async with _sem:
        return await _save_message(client, chat, msg)


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
    tasks: list[asyncio.Task[Path]] = []
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


async def refetch_broken(client: TelegramClient) -> None:
    """Re-fetch messages listed in ``BROKEN_META_FILE``."""
    if not BROKEN_META_FILE.exists():
        return
    broken = load_json(BROKEN_META_FILE)
    if broken is None:
        log.error("Failed to parse broken metadata file")
        return
    if not isinstance(broken, list):
        return
    remaining = []
    for item in broken:
        chat = item.get("chat")
        mid = item.get("id")
        if not chat or not mid:
            continue
        try:
            msg = await client.get_messages(chat, ids=int(mid))
            if msg:
                await _save_bounded(client, chat, msg)
                log.info("Refetched message", chat=chat, id=mid)
            else:
                remaining.append(item)
        except Exception:
            log.exception("Failed to refetch", chat=chat, id=mid)
            remaining.append(item)
    if remaining:
        write_json(BROKEN_META_FILE, remaining)
    else:
        BROKEN_META_FILE.unlink()


async def refetch_misparsed(client: TelegramClient) -> None:
    """Re-fetch messages listed in ``MISPARSED_FILE`` and drop lots if they change."""
    if not MISPARSED_FILE.exists():
        return
    items = load_json(MISPARSED_FILE)
    if not isinstance(items, list):
        return
    for entry in items:
        lot = entry.get("lot", {}) if isinstance(entry, dict) else {}
        chat = lot.get("source:chat")
        mid = lot.get("source:message_id")
        path_rel = lot.get("source:path")
        if not chat or not mid:
            continue
        old_path = RAW_DIR / path_rel if path_rel else None
        old_text = old_path.read_text() if old_path and old_path.exists() else None
        try:
            msg = await client.get_messages(chat, ids=int(mid))
        except Exception:
            log.exception("Failed to refetch", chat=chat, id=mid)
            continue
        if not msg:
            continue
        new_path = await _save_bounded(client, chat, msg)
        if old_text is None:
            continue
        try:
            new_text = new_path.read_text()
        except Exception:
            continue
        if new_text != old_text or new_path != old_path:
            lot_path = LOTS_DIR / new_path.relative_to(RAW_DIR).with_suffix(".json")
            if lot_path.exists():
                lot_path.unlink()
                log.info("Dropped lots after refetch", file=str(lot_path))


async def refetch_empty(client: TelegramClient) -> None:
    """Re-fetch posts missing both text and images."""
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
        old_text = path.read_text()
        try:
            msg = await client.get_messages(chat, ids=int(mid))
        except Exception:
            log.exception("Failed to refetch", chat=chat, id=mid)
            continue
        if not msg:
            continue
        new_path = await _save_bounded(client, chat, msg)
        try:
            new_text = new_path.read_text()
        except Exception:
            continue
        if new_text != old_text or new_path != path:
            lot_path = LOTS_DIR / new_path.relative_to(RAW_DIR).with_suffix(".json")
            if lot_path.exists():
                lot_path.unlink()
                log.info("Dropped lots after refetch", file=str(lot_path))


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
            async for msg in client.iter_messages(chat, offset_date=start_date, reverse=True):
                if msg.date >= end_date:
                    break
                path = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}" / f"{msg.id}.md"
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
    global _sem
    _sem = asyncio.Semaphore(DOWNLOAD_WORKERS)
    _mark_activity()

    await ensure_chat_access(client)

    await refetch_broken(client)
    await refetch_misparsed(client)
    await refetch_empty(client)

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
