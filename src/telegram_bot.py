import asyncio
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config_utils import load_config
from log_utils import get_logger, install_excepthook
import gettext
import json
from typing import Any

from lot_io import get_lot
from similar_utils import _cos_sim, _load_embeddings

log = get_logger().bind(script=__file__)
install_excepthook(log)

cfg = load_config()

_translators: dict[str, gettext.NullTranslations] = {}


def _t(lang: str, text: str) -> str:
    """Return ``text`` translated to ``lang`` using gettext files."""
    trans = _translators.get(lang)
    if trans is None:
        try:
            trans = gettext.translation(
                "messages", localedir="locale", languages=[lang]
            )
        except Exception:
            trans = gettext.NullTranslations()
        _translators[lang] = trans
    return trans.gettext(text)

# File paths
PROFILES_PATH = Path("data/bot_profiles.json")
STATE_PATH = Path("data/bot_state.json")
EMBED_DIR = Path("data/embeddings")
LOTS_DIR = Path("data/lots")

profiles: dict[str, dict[str, Any]] = {}
processed_ids: set[str] = set()
embeddings: dict[str, list[float]] = {}


def ensure_profile(uid: str) -> dict[str, Any]:
    """Return profile for ``uid`` creating one if needed."""
    prof = profiles.get(uid)
    if prof is None:
        prof = {"lang": cfg.LANGS[0], "likes": [], "dislikes": [], "queue": []}
        profiles[uid] = prof
        save_profiles()
    return prof


def load_profiles() -> None:
    """Populate the global ``profiles`` mapping."""
    global profiles
    if PROFILES_PATH.exists():
        try:
            profiles = json.loads(PROFILES_PATH.read_text())
        except Exception:
            log.exception("Failed to read profiles")
            profiles = {}


def save_profiles() -> None:
    """Write ``profiles`` to disk."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(profiles, ensure_ascii=False))


def load_state() -> None:
    """Populate ``processed_ids`` from ``STATE_PATH``."""
    global processed_ids
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text())
            processed_ids = set(data.get("processed", []))
        except Exception:
            log.exception("Failed to read bot state")
            processed_ids = set()


def save_state() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"processed": sorted(processed_ids)}))


def scan_embeddings() -> list[str]:
    """Load new embeddings and return list of new lot ids."""
    new_map = _load_embeddings()
    new_ids = [lid for lid in new_map if lid not in embeddings and lid not in processed_ids]
    embeddings.update(new_map)
    return new_ids




def _should_suggest(profile: dict, vec: list[float]) -> bool:
    likes = [embeddings.get(i) for i in profile.get("likes", []) if embeddings.get(i)]
    dislikes = [embeddings.get(i) for i in profile.get("dislikes", []) if embeddings.get(i)]
    if not likes and not dislikes:
        return True
    like_score = max((_cos_sim(vec, v) for v in likes), default=0)
    dislike_score = max((_cos_sim(vec, v) for v in dislikes), default=0)
    return like_score >= dislike_score


def enqueue_new_ids(ids: list[str]) -> None:
    for lot_id in ids:
        vec = embeddings.get(lot_id)
        if vec is None:
            continue
        for uid, prof in profiles.items():
            queue = prof.setdefault("queue", [])
            if (
                lot_id in queue
                or lot_id in prof.get("likes", [])
                or lot_id in prof.get("dislikes", [])
            ):
                continue
            if _should_suggest(prof, vec):
                queue.append(lot_id)
    if ids:
        save_profiles()


async def _send_queue(app) -> None:
    """Send next lot from each user queue via ``app``."""
    for uid, prof in profiles.items():
        queue = prof.get("queue") or []
        if not queue:
            continue
        lot_id = queue.pop(0)
        lot = get_lot(lot_id, LOTS_DIR)
        if not lot:
            continue
        lang = prof.get("lang", cfg.LANGS[0])
        text = (
            lot.get(f"title_{lang}")
            or lot.get("title_en")
            or lot_id
        )
        buttons = [
            [
                InlineKeyboardButton("👍", callback_data=f"like:{lot_id}"),
                InlineKeyboardButton("👎", callback_data=f"dislike:{lot_id}"),
            ]
        ]
        try:
            await app.bot.send_message(
                chat_id=int(uid),
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            log.exception("Failed to send lot", user=uid, id=lot_id)
        await asyncio.sleep(0.1)
    save_profiles()


async def send_alert(text: str) -> None:
    """Broadcast ``text`` to all registered users."""
    load_profiles()
    ids = [int(uid) for uid in profiles.keys()]
    if not ids:
        return
    log.info("Sending alert", count=len(ids))
    app = ApplicationBuilder().token(cfg.TG_TOKEN).build()
    for uid in ids:
        try:
            await app.bot.send_message(chat_id=uid, text=text)
        except Exception:
            log.exception("Failed alert", user=uid)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user and confirm startup."""
    uid = str(update.effective_user.id)
    prof = ensure_profile(uid)
    lang = prof.get("lang", cfg.LANGS[0])
    await update.message.reply_text(_t(lang, "Registered"))


async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set preferred language or list available choices."""
    uid = str(update.effective_user.id)
    prof = ensure_profile(uid)
    if not context.args:
        msg = _t(prof.get("lang", cfg.LANGS[0]), "Current: %(lang)s. Options: %(langs)s")
        await update.message.reply_text(msg % {"lang": prof.get("lang"), "langs": ", ".join(cfg.LANGS)})
        return
    lang = context.args[0].lower()
    if lang not in cfg.LANGS:
        msg = _t(prof.get("lang", cfg.LANGS[0]), "Unknown lang. Choices: %(langs)s")
        await update.message.reply_text(msg % {"langs": ", ".join(cfg.LANGS)})
        return
    prof["lang"] = lang
    save_profiles()
    await update.message.reply_text(_t(lang, "Language set to %(lang)s") % {"lang": lang})


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses for lot feedback."""
    if not update.callback_query:
        return
    uid = str(update.effective_user.id)
    data = update.callback_query.data or ""
    action, lot_id = (data.split(":", 1) + ["", ""])[:2]
    prof = ensure_profile(uid)
    if action == "like":
        prof.setdefault("likes", []).append(lot_id)
        if lot_id in prof.get("dislikes", []):
            prof["dislikes"].remove(lot_id)
    elif action == "dislike":
        prof.setdefault("dislikes", []).append(lot_id)
        if lot_id in prof.get("likes", []):
            prof["likes"].remove(lot_id)
    save_profiles()
    await update.callback_query.answer(_t(prof.get("lang", cfg.LANGS[0]), "Noted"))


async def main() -> None:
    """Run the Telegram recommendation bot."""
    load_profiles()
    load_state()
    scan_embeddings()
    app = ApplicationBuilder().token(cfg.TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CallbackQueryHandler(vote_callback))

    async def ticker() -> None:
        while True:
            new_ids = scan_embeddings()
            enqueue_new_ids(new_ids)
            processed_ids.update(new_ids)
            save_state()
            await _send_queue(app)
            await asyncio.sleep(5)

    asyncio.create_task(ticker())
    log.info("Bot started")
    await app.run_polling()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "alert":
        asyncio.run(send_alert(" ".join(sys.argv[2:])))
    else:
        asyncio.run(main())
