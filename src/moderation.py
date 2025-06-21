from __future__ import annotations
"""Simple moderation checks for raw posts and lots."""

from pathlib import Path
import json

from log_utils import get_logger

log = get_logger().bind(module=__name__)

# Phrases that indicate spam or irrelevant posts.  The check is case insensitive
# so new variations are still caught.
BANNED_SUBSTRINGS = [
    "прошу подпишитесь на канал @flats_in_georgia чтобы я пропускал ваши сообщения в этот чат!",
    "нарушил допустимую частоту публикации обьявлений и не сможет писать до",
    "вы используете запрещенное слово"
]

RAW_DIR = Path("data/raw")
LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")


def _parse_md(path: Path) -> tuple[dict, str]:
    """Return metadata dictionary and body text from ``path``."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    meta: dict[str, str] = {}
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


def should_skip_text(text: str) -> bool:
    """Return ``True`` if ``text`` contains banned phrases."""
    lower = text.lower()
    for phrase in BANNED_SUBSTRINGS:
        if phrase.lower() in lower:
            return True
    return False


def should_skip_message(meta: dict, text: str) -> bool:
    """Return ``True`` when the raw Telegram message should be ignored."""
    if should_skip_text(text):
        log.debug("Message rejected", id=meta.get("id"))
        return True
    return False


def should_skip_lot(lot: dict) -> bool:
    """Return ``True`` when the lot fails additional checks."""
    if lot.get("contact:telegram") == "@username":
        log.debug("Lot rejected", reason="example contact")
        return True
    return False


def apply_to_history() -> None:
    """Remove processed lots now failing moderation."""
    removed = 0
    for path in LOTS_DIR.rglob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            log.exception("Failed to parse lot file", file=str(path))
            continue
        items = data if isinstance(data, list) else [data]
        src = items[0].get("source:path")
        raw = RAW_DIR / src if src else None
        if not raw or not raw.exists():
            continue
        _, text = _parse_md(raw)
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
