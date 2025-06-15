"""Telegram bot that alerts subscribers about new lots."""

import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

from config import TG_TOKEN
from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

SUBSCRIBERS = Path("data/subscribers.txt")
LOTS_DIR = Path("data/lots")


def load_subscribers() -> set[int]:
    if not SUBSCRIBERS.exists():
        return set()
    return {int(x) for x in SUBSCRIBERS.read_text().split()}


def save_subscribers(ids: set[int]) -> None:
    SUBSCRIBERS.write_text("\n".join(str(i) for i in sorted(ids)))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = load_subscribers()
    subs.add(update.effective_user.id)
    save_subscribers(subs)
    await update.message.reply_text("Subscribed to alerts")


async def send_alert(text: str) -> None:
    subs = load_subscribers()
    if not subs:
        return
    application = ApplicationBuilder().token(TG_TOKEN).build()
    for uid in subs:
        try:
            await application.bot.send_message(chat_id=uid, text=text)
        except Exception:
            log.exception("Failed alert", user=uid)


async def main() -> None:
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    log.info("Alert bot started")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
