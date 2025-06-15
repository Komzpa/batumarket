"""Telegram bot that mirrors messages from configured chats.

It stores raw text and media in ``data/raw`` and ``data/media``.  Edits are
appended as extra markdown blocks so nothing is lost.
"""

import asyncio
import hashlib
import base64
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from log_utils import get_logger, install_excepthook
from notes_utils import write_md
from config import TG_TOKEN, CHATS

log = get_logger().bind(script=__file__)
install_excepthook(log)

RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")


def _save_text(chat: int, message_id: int, text: str) -> None:
    path = RAW_DIR / str(chat) / f"{message_id}.md"
    write_md(path, text)
    log.debug("Wrote message", path=str(path))


def _save_media(file_bytes: bytes) -> str:
    sha = hashlib.sha256(file_bytes).hexdigest()
    path = MEDIA_DIR / sha
    if not path.exists():
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        log.debug("Stored media", sha=sha)
    return sha


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if chat_id not in CHATS:
        return

    text = msg.text or msg.caption or ""
    _save_text(chat_id, msg.message_id, text)

    if msg.photo:
        file = await msg.photo[-1].get_file()  # highest quality
        data = await file.download_as_bytearray()
        _save_media(bytes(data))


async def main() -> None:
    application = ApplicationBuilder().token(TG_TOKEN).build()
    handler = MessageHandler(filters.ALL, handle_message)
    application.add_handler(handler)

    log.info("Starting bot")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
