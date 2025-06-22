from __future__ import annotations

"""Read and write raw Telegram posts stored as Markdown."""

from pathlib import Path
from datetime import datetime, timezone

from log_utils import get_logger
from serde_utils import parse_md, write_md, read_md
import ast


def _parse_block(text: str) -> tuple[dict[str, str], str]:
    """Return metadata dict and remaining body from ``text``."""
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
    text = read_md(path)
    meta_all: list[dict[str, str]] = []
    rest = text
    while rest:
        meta, rest_body = _parse_block(rest)
        if not meta:
            break
        meta_all.append(meta)
        lines = rest_body.lstrip().splitlines()
        if not lines:
            rest = ""
            break
        first = lines[0]
        key = first.split(":", 1)[0].strip() if ":" in first else ""
        if key and key in meta:
            rest = rest_body.lstrip()
            continue
        rest = rest_body
        break

    if not meta_all:
        return {}, rest

    meta = meta_all[0]
    for extra in meta_all[1:]:
        for k, v in extra.items():
            if k == "files":
                base = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
                add = ast.literal_eval(v) if isinstance(v, str) else v
                merged = list(dict.fromkeys(base + add))
                meta["files"] = str(merged)
            else:
                assert meta.get(k) == v, f"mismatched header {k} in {path}"

    for k, v in list(meta.items()):
        if isinstance(v, str) and v.isdigit():
            meta[k] = int(v)

    return meta, rest.strip()


def write_post(path: Path, meta: dict[str, str], body: str) -> None:
    """Write metadata and body as a Markdown post."""
    assert get_timestamp(meta) is not None, "date required"
    assert get_contact(meta) is not None, "contact required"
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    lines = body.strip().splitlines()
    if lines:
        first = lines[0]
        key = first.split(":", 1)[0].strip() if ":" in first else ""
        if key and key in meta:
            raise AssertionError("body contains duplicated headers")
    write_md(path, "\n".join(meta_lines) + "\n\n" + body.strip())
    log.debug("Wrote post", path=str(path))

