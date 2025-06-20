"""Mirror Telegram chats using a user account via Telethon."""

import asyncio
import hashlib
import ast
from pathlib import Path
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
from telethon.tl.custom import Message
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError

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
from log_utils import get_logger, install_excepthook
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
    subdir = RAW_DIR / chat / f"{msg.date:%Y}" / f"{msg.date:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    files = []
    if msg.media:
        data = await msg.download_media(bytes)
        files.append(await _save_media(chat, msg, data))

    permissions = None
    try:
        permissions = await client.get_permissions(chat, msg.sender_id)
    except Exception:
        log.debug("Failed to fetch permissions", chat=chat, user=msg.sender_id)

    sender = await msg.get_sender()
    meta = {
        "id": msg.id,
        "chat": chat,
        "sender": msg.sender_id,
        "sender_name": " ".join(
            p for p in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if p
        ) or None,
        "sender_username": getattr(sender, "username", None),
        "sender_phone": getattr(sender, "phone", None),
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
        group_path = _GROUPS.get(msg.grouped_id)
        if not group_path:
            group_path = subdir / f"{msg.id}.md"
            _GROUPS[msg.grouped_id] = group_path
        else:
            meta_prev, body_prev = _parse_md(group_path)
            files_prev = ast.literal_eval(meta_prev.get("files", "[]")) if "files" in meta_prev else []
            files = files_prev + files
            meta_prev.update(meta)
            meta_prev["files"] = files
            meta = meta_prev
            text = body_prev or text
    path = group_path or subdir / f"{msg.id}.md"
    _write_md(path, meta, text)
    log.debug("Wrote message", path=str(path))


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
        log.debug("Stored media", sha=sha)
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
        last_id = get_last_id(chat)
        first_id = get_first_id(chat)
        last_date = _get_id_date(chat, last_id) if last_id else None
        first_date = _get_id_date(chat, first_id) if first_id else None

        # Decide whether to fetch newer or older messages.
        if first_date is None or first_date > cutoff:
            start_date = cutoff if first_date is None else max(cutoff, first_date - timedelta(days=1))
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
        else:
            start_date = last_date or cutoff
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


async def main() -> None:
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
