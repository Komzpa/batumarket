from __future__ import annotations
"""Simple moderation checks for raw posts and lots."""

from pathlib import Path
import json
import ast

from log_utils import get_logger
from post_io import (
    read_post,
    raw_post_path,
    RAW_DIR,
    get_contact as get_post_contact,
    get_timestamp as get_post_timestamp,
)
from scan_ontology import REVIEW_FIELDS
from lot_io import read_lots, get_seller, get_timestamp

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
    "mdma",
    "cтоимость рекламного пакета в нашей группе по тематике",
    "желающие снять квартиру в лучших, надежных и эффективных группах могут подписаться"
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
    'chatassist_bot',
    'verifuma_bot',
    'razvitiekanala_bot',
    'aboniment_admin1'
]

LOTS_DIR = Path("data/lots")
EMBED_DIR = Path("data/embeddings")


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


def message_skip_reason(meta: dict, text: str) -> str | None:
    """Return the moderation reason for ``meta`` and ``text`` or ``None``."""
    if meta.get("skipped_media"):
        return "skipped-media"
    if should_skip_user(meta.get("sender_username")):
        return "blacklisted-user"
    if should_skip_text(text):
        return "banned-text"
    files: list[str] = []
    if "files" in meta:
        val = meta.get("files")
        try:
            if isinstance(val, str):
                files = ast.literal_eval(val)
            elif isinstance(val, list):
                files = val
            else:
                raise ValueError("bad files type")
        except Exception:
            log.debug("Bad file list", value=val, id=meta.get("id"))
    if not text.strip() and not files:
        return "empty"
    return None


def should_skip_message(meta: dict, text: str) -> bool:
    """Return ``True`` when the raw Telegram message should be ignored."""
    reason = message_skip_reason(meta, text)
    if reason:
        log.debug("Message rejected", reason=reason, id=meta.get("id"))
        return True
    return False


def lot_skip_reason(lot: dict) -> str | None:
    """Return the moderation reason for ``lot`` or ``None``."""
    # Fraud overrides every other rule so the lot can be filtered even when
    # translations are missing.
    if lot.get("fraud") is not None:
        return "fraud"
    # Placeholder contacts from examples do not belong on the website.
    if lot.get("contact:telegram") == "@username":
        return "example contact"
    if any(not lot.get(f) for f in REVIEW_FIELDS):
        return "missing translation"
    return None


def should_skip_lot(lot: dict) -> bool:
    """Return ``True`` when the lot fails additional checks."""
    reason = lot_skip_reason(lot)
    if reason:
        log.debug("Lot rejected", reason=reason, id=lot.get("_id"))
        return True
    return False


def is_misparsed(lot: dict, meta: dict | None = None) -> bool:
    """Return ``True`` for obviously invalid lots or source posts."""
    if lot.get("contact:telegram") == "@username":
        log.debug("Example contact", id=lot.get("_id"))
        return True
    if get_timestamp(lot) is None:
        log.debug("Missing timestamp", id=lot.get("_id"))
        return True
    if get_seller(lot) is None:
        log.debug("Missing seller info", id=lot.get("_id"))
        return True
    if meta is not None:
        if get_post_timestamp(meta) is None:
            log.debug("Missing raw timestamp", id=lot.get("_id"))
            return True
        if get_post_contact(meta) is None:
            log.debug("Missing raw contact", id=lot.get("_id"))
            return True
    if any(not lot.get(f) for f in REVIEW_FIELDS):
        log.debug("Missing translations", id=lot.get("_id"))
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
        raw = raw_post_path(src) if src else None
        if not raw or not raw.exists():
            continue
        _, text = read_post(raw)
        skip = should_skip_message(items[0], text) or any(
            should_skip_lot(l) for l in items
        )
        if skip:
            path.unlink()
            vec = (EMBED_DIR / path.relative_to(LOTS_DIR)).with_suffix(".json")
            if vec.exists():
                vec.unlink()
            removed += 1
            log.info("Removed lot", file=str(path))
    if removed:
        log.info("Moderation removed lots", count=removed)


if __name__ == "__main__":
    apply_to_history()
