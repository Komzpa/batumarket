"""Mirror Telegram chats using a user account via Telethon."""

import asyncio
import hashlib
from pathlib import Path

from telethon import TelegramClient, events

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

RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")


def get_last_id(chat: str) -> int:
    """Return the highest saved message id for ``chat``."""
    chat_dir = RAW_DIR / chat
    if not chat_dir.exists():
        return 0
    ids = []
    for p in chat_dir.glob("*.md"):
        try:
            ids.append(int(p.stem))
        except ValueError:
            log.debug("Ignoring file", file=str(p))
    return max(ids) if ids else 0


def _save_text(chat: str, message_id: int, text: str) -> None:
    path = RAW_DIR / chat / f"{message_id}.md"
    write_md(path, text)
    log.debug("Wrote message", path=str(path))


def _save_media(data: bytes) -> str:
    sha = hashlib.sha256(data).hexdigest()
    path = MEDIA_DIR / sha
    if not path.exists():
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log.debug("Stored media", sha=sha)
    return sha


async def fetch_missing(client: TelegramClient) -> None:
    """Pull any messages newer than the last saved one."""
    for chat in CHATS:
        last_id = get_last_id(chat)
        count = 0
        async for msg in client.iter_messages(chat, min_id=last_id, reverse=True):
            text = msg.message or ""
            _save_text(chat, msg.id, text)
            if msg.media:
                data = await msg.download_media(bytes)
                _save_media(data)
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
        text = event.message.message or ""
        _save_text(chat, event.message.id, text)
        if event.message.media:
            data = await event.message.download_media(bytes)
            _save_media(data)

    @client.on(events.MessageEdited(chats=CHATS))
    async def edit_handler(event):
        chat = event.chat.username or str(event.chat_id)
        text = event.message.message or ""
        _save_text(chat, event.message.id, text)
        if event.message.media:
            data = await event.message.download_media(bytes)
            _save_media(data)
        log.debug("Saved edit", chat=chat, id=event.message.id)

    log.info("Client started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
