"""Mirror Telegram chats using a user account via Telethon."""

import asyncio
import hashlib
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.custom import Message

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

# Messages are stored as Markdown with metadata under
# data/raw/<chat>/<YYYY>/<MM>/<id>.md.  Media files live under
# data/media/<chat>/<YYYY>/<MM>/ using their SHA-256 hash plus extension.
RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")


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

    meta = {
        "id": msg.id,
        "chat": chat,
        "sender": msg.sender_id,
        "date": msg.date.isoformat(),
        "reply_to": msg.reply_to_msg_id,
        "is_admin": getattr(permissions, "is_admin", False),
    }
    if files:
        meta["files"] = files

    # Metadata is stored as simple "key: value" pairs followed by the original
    # message text so other scripts can easily parse it.
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    path = subdir / f"{msg.id}.md"
    text = msg.message or ""
    write_md(path, "\n".join(meta_lines) + "\n\n" + text)
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


async def fetch_missing(client: TelegramClient) -> None:
    """Pull any messages newer than the last saved one."""
    for chat in CHATS:
        last_id = get_last_id(chat)
        count = 0
        async for msg in client.iter_messages(chat, min_id=last_id, reverse=True):
            await _save_message(client, chat, msg)
            count += 1
        log.info("Synced chat", chat=chat, new_messages=count)


async def main() -> None:
    client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
    await client.start()
    log.info("Logged in")

    await fetch_missing(client)
    log.info("Initial sync complete; listening for updates")

    @client.on(events.NewMessage(chats=CHATS))
    async def handler(event):
        chat = event.chat.username or str(event.chat_id)
        await _save_message(client, chat, event.message)

    @client.on(events.MessageEdited(chats=CHATS))
    async def edit_handler(event):
        chat = event.chat.username or str(event.chat_id)
        await _save_message(client, chat, event.message)
        log.debug("Saved edit", chat=chat, id=event.message.id)

    log.info("Client started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
