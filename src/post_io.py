from __future__ import annotations

"""Read and write raw Telegram posts stored as Markdown."""

from pathlib import Path
from datetime import datetime, timezone

from log_utils import get_logger
from notes_utils import write_md, read_md, _parse_block

RAW_DIR = Path("data/raw")
import ast

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
    # Posts may include multiple header sections separated by blank lines.
    # Keep stripping them until we encounter the actual body text.
    while rest:
        meta, rest_body = _parse_block(rest)
        if not meta:
            break
        meta_all.append(meta)
        # Inspect the beginning of the remaining text to check if another
        # header block follows.
        lines = rest_body.lstrip().splitlines()
        if not lines:
            rest = ""
            break
        first = lines[0]
        key = first.split(":", 1)[0].strip() if ":" in first else ""
        # A line starting with ``key:`` that matches an existing header key
        # indicates another header section rather than the body.
        if key and key in meta:
            new_rest = rest_body.lstrip()
            if new_rest == rest:
                # Avoid infinite loops when the body starts with a duplicate
                # header. If stripping whitespace does not advance ``rest``
                # simply drop the remaining text and stop parsing.
                if "\n" in rest_body:
                    rest = ""
                else:
                    rest = rest_body
                break
            # Another header block follows. Continue parsing with the
            # stripped remainder.
            rest = new_rest
            continue
        rest = rest_body
        break

    if not meta_all:
        return {}, rest

    meta = meta_all[0]
    # Later header blocks should only repeat data. ``files`` may contain new
    # entries which we merge, other keys must match exactly.
    for extra in meta_all[1:]:
        for k, v in extra.items():
            if k == "files":
                base = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
                add = ast.literal_eval(v) if isinstance(v, str) else v
                merged = list(dict.fromkeys(base + add))
                meta["files"] = str(merged)
            else:
                assert meta.get(k) == v, f"mismatched header {k} in {path}"

    # Convert digit-only values to integers for convenience.
    for k, v in list(meta.items()):
        if isinstance(v, str) and v.isdigit():
            meta[k] = int(v)

    if "files" in meta:
        try:
            files = ast.literal_eval(meta["files"]) if isinstance(meta["files"], str) else meta["files"]
            if isinstance(files, list):
                # Remove duplicates while preserving order.
                dedup = list(dict.fromkeys(files))
                if len(dedup) != len(files):
                    log.debug(
                        "Deduplicated files", path=str(path), before=len(files), after=len(dedup)
                    )
                meta["files"] = str(dedup)
        except Exception:
            log.debug("Invalid files", path=str(path))

    # ``rest`` now contains the body text without surrounding whitespace.
    return meta, rest.strip()


def write_post(path: Path, meta: dict[str, str], body: str) -> None:
    """Write metadata and body as a Markdown post."""
    assert get_timestamp(meta) is not None, "date required"
    assert get_contact(meta) is not None, "contact required"
    if "files" in meta:
        files = meta["files"]
        if isinstance(files, list):
            assert len(files) == len(set(files)), "duplicate files"
        elif isinstance(files, str):
            try:
                parsed = ast.literal_eval(files)
            except Exception:
                parsed = []
            if isinstance(parsed, list):
                assert len(parsed) == len(set(parsed)), "duplicate files"
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    lines = body.strip().splitlines()
    if lines:
        first = lines[0]
        key = first.split(":", 1)[0].strip() if ":" in first else ""
        if key and key in meta:
            raise AssertionError("body contains duplicated headers")
    write_md(path, "\n".join(meta_lines) + "\n\n" + body.strip())
    log.debug("Wrote post", path=str(path))


def raw_post_path(rel: str | Path, root: Path = RAW_DIR) -> Path:
    """Return absolute message path for ``rel`` under ``root``."""
    return root / Path(rel)


def raw_post_path_from_lot(lot: dict, root: Path = RAW_DIR) -> Path | None:
    """Return raw post path referenced by ``lot`` or ``None``."""
    rel = lot.get("source:path")
    if not rel:
        return None
    return raw_post_path(rel, root)

