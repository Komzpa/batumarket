from __future__ import annotations
"""Simple moderation checks for raw posts and lots."""

from pathlib import Path
import json
import ast

from log_utils import get_logger
from post_io import read_post
from scan_ontology import REVIEW_FIELDS
from lot_io import read_lots

log = get_logger().bind(module=__name__)

# Phrases that indicate spam or irrelevant posts.  The check is case insensitive
# so new variations are still caught.
BANNED_SUBSTRINGS = [
    "прошу подпишитесь на канал @flats_in_georgia чтобы я пропускал ваши сообщения в этот чат!",
    "нарушил допустимую частоту публикации обьявлений и не сможет писать до",
    "вы используете запрещенное слово",
    "ищу людей на неполный рабочий день",
    "ищу людей для легкой работы, оплата хорошая",
    "ищу людей для легкοй рабοты, оплата хорошая",
    "наркотики",
    "кокаин",
    "героин",
    "спайс",
    "mdma"
]

# Telegram usernames that only post housekeeping messages.  Their updates are
# ignored entirely so we do not waste time downloading captcha images or other
# irrelevant content.  All names must be lower case for easy comparison.
BLACKLISTED_USERS = [
    "m_s_help_bot",
    "chatkeeperbot",
    "dosvidulibot",
    "batumi_batumi_bot",
    'ghclone3bot',
    'grouphelpbot',
    'ghclone2bot',
    'ghclone1bot',
    'ghclone4bot',
    'ghclone5bot',
    'ghclone6bot',
    'ghclone7bot',
    'chatassist_bot'
]

RAW_DIR = Path("data/raw")
LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")


def should_skip_text(text: str) -> bool:
    """Return ``True`` if ``text`` contains banned phrases."""
    lower = text.lower()
    for phrase in BANNED_SUBSTRINGS:
        if phrase.lower() in lower:
            return True
    return False


def should_skip_user(username: str | None) -> bool:
    """Return ``True`` if ``username`` is blacklisted."""
    if not username:
        return False
    return username.lower() in BLACKLISTED_USERS


def should_skip_message(meta: dict, text: str) -> bool:
    """Return ``True`` when the raw Telegram message should be ignored."""
    if meta.get("skipped_media"):
        log.debug("Message rejected", reason="skipped-media", id=meta.get("id"))
        return True
    if should_skip_user(meta.get("sender_username")):
        log.debug("Message rejected", reason="blacklisted-user", user=meta.get("sender_username"))
        return True
    if should_skip_text(text):
        log.debug("Message rejected", id=meta.get("id"))
        return True
    files: list[str] = []
    if "files" in meta:
        try:
            files = ast.literal_eval(meta.get("files", "[]"))
        except Exception:
            log.debug("Bad file list", value=meta.get("files"), id=meta.get("id"))
    if not text.strip() and not files:
        log.debug("Message rejected", reason="empty", id=meta.get("id"))
        return True
    return False


def should_skip_lot(lot: dict) -> bool:
    """Return ``True`` when the lot fails additional checks."""
    if lot.get("fraud") is not None:
        log.debug("Lot rejected", reason="fraud", id=lot.get("_id"))
        return True
    if lot.get("contact:telegram") == "@username":
        log.debug("Lot rejected", reason="example contact")
        return True
    if any(not lot.get(f) for f in REVIEW_FIELDS):
        log.debug("Lot rejected", reason="missing translation", id=lot.get("_id"))
        return True
    return False


def apply_to_history() -> None:
    """Remove processed lots now failing moderation."""
    removed = 0
    for path in LOTS_DIR.rglob("*.json"):
        items = read_lots(path)
        if not items:
            continue
        src = items[0].get("source:path")
        raw = RAW_DIR / src if src else None
        if not raw or not raw.exists():
            continue
        _, text = read_post(raw)
        skip = should_skip_message(items[0], text) or any(
            should_skip_lot(l) for l in items
        )
        if skip:
            path.unlink()
            vec = (VEC_DIR / path.relative_to(LOTS_DIR)).with_suffix(".json")
            if vec.exists():
                vec.unlink()
            removed += 1
            log.info("Removed lot", file=str(path))
    if removed:
        log.info("Moderation removed lots", count=removed)


if __name__ == "__main__":
    apply_to_history()
