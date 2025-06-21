from __future__ import annotations

"""Read and write raw Telegram posts stored as Markdown."""

from pathlib import Path
from datetime import datetime, timezone

from log_utils import get_logger
from serde_utils import parse_md, write_md

log = get_logger().bind(module=__name__)


POST_CONTACT_FIELDS = [
    "sender_phone",
    "sender_username",
    "post_author",
    "tg_link",
    "sender_name",
]


def get_contact(meta: dict) -> str | None:
    """Return a contact identifier from ``meta`` or ``None`` when missing."""
    for key in POST_CONTACT_FIELDS:
        value = meta.get(key)
        if value:
            return str(value)
    return None


def get_timestamp(meta: dict) -> datetime | None:
    """Return ``meta['date']`` as a timezone-aware ``datetime``."""
    ts = meta.get("date")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except Exception:
        log.debug("Bad timestamp", value=ts, id=meta.get("id"))
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if dt > now:
        log.debug("Future timestamp", value=ts, id=meta.get("id"))
        return None
    return dt


def read_post(path: Path) -> tuple[dict[str, str], str]:
    """Return metadata dictionary and body text for ``path``."""
    meta, text = parse_md(path)
    for k, v in list(meta.items()):
        if isinstance(v, str) and v.isdigit():
            meta[k] = int(v)
    return meta, text


def write_post(path: Path, meta: dict[str, str], body: str) -> None:
    """Write metadata and body as a Markdown post."""
    assert get_timestamp(meta) is not None, "date required"
    assert get_contact(meta) is not None, "contact required"
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    write_md(path, "\n".join(meta_lines) + "\n\n" + body.strip())
    log.debug("Wrote post", path=str(path))

