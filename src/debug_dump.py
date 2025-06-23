#!/usr/bin/env python
"""Collect debug info for a single lot.

The script accepts a URL pointing to a generated HTML page and gathers
all related files for that lot.  The Telegram client is invoked with
``--fetch`` so message metadata can be refreshed.  Logs, lots, vectors
and raw posts are concatenated into a single output suitable for
copy/paste when troubleshooting the pipeline.  If the JSON describing
the lot is missing, the chat name and message ID are derived from the
URL path so Telegram can still be queried.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from caption_io import (
    read_caption,
    caption_json_path,
    caption_md_path,
    has_caption,
)
from serde_utils import read_text, load_json
from lot_io import parse_lot_id as split_lot_id, lot_json_path
from log_utils import get_logger
from post_io import read_post, raw_post_path, RAW_DIR
import ast
import moderation
from scan_ontology import REVIEW_FIELDS

log = get_logger().bind(script=__file__)

LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")
MEDIA_DIR = Path("data/media")


def parse_url(url: str) -> tuple[str, str | None]:
    """Return ``(lot_id, lang)`` extracted from ``url``."""
    path = urlparse(url).path.lstrip("/")
    # Generated pages always end with ``.html`` so trim that off.
    if path.endswith(".html"):
        path = path[:-5]
    # Language code, if any, sits after the last underscore in the page name.
    if "_" in path:
        lot_id, lang = path.rsplit("_", 1)
    else:
        lot_id, lang = path, None
    return lot_id, lang


def guess_source_from_lot(lot_id: str) -> tuple[str | None, int | None]:
    """Guess ``(chat, message_id)`` directly from ``lot_id``."""
    rel, _ = split_lot_id(lot_id)
    parts = rel.parts
    chat = parts[0] if parts else None
    last = rel.name
    try:
        mid = int(last)
    except ValueError:
        mid = None
    return chat, mid


def load_source_info(lot_id: str) -> tuple[str | None, int | None]:
    """Return ``(chat, message_id)`` for ``lot_id`` if available."""
    lot_path = lot_json_path(lot_id, LOTS_DIR)
    lot_data = load_json(lot_path)
    if not lot_data:
        log.warning("Lot file missing", lot=lot_id)
        return None, None
    lot = lot_data[0] if isinstance(lot_data, list) else lot_data
    chat = lot.get("source:chat")
    mid = lot.get("source:message_id")
    if (chat is None or mid is None) and lot.get("source:path"):
        # In older pipeline versions the raw file path was the only link back
        # to the source message. When present use it as a secondary lookup.
        parts = Path(str(lot["source:path"])).parts
        if len(parts) >= 4:
            chat = chat or parts[0]
            try:
                mid = mid or int(Path(parts[-1]).stem)
            except ValueError:
                mid = None
    return chat, mid


def run_tg_fetch(chat: str, mid: int) -> str:
    """Run ``tg_client.py --fetch`` and return combined logs."""
    env = os.environ.copy()
    env.setdefault("LOG_LEVEL", "DEBUG")
    if env.get("TEST_MODE") == "1":
        return "TEST_MODE enabled, skipping Telegram fetch\n"
    log_file = Path("errors.log")
    if log_file.exists():
        log_file.unlink()
    proc = subprocess.run(
        [sys.executable, "src/tg_client.py", "--fetch", chat, str(mid)],
        env=env,
        capture_output=True,
        text=True,
    )
    output = proc.stdout
    if proc.stderr:
        output += "\n" + proc.stderr
    if log_file.exists():
        output += "\n" + read_text(log_file)
        log_file.unlink()
    return output


def collect_files(lot_id: str) -> list[tuple[str, str]]:
    """Return ``[(name, content), ...]`` for files related to ``lot_id``."""
    files: list[tuple[str, str]] = []
    lot_file = lot_json_path(lot_id, LOTS_DIR)
    if lot_file.exists():
        files.append((str(lot_file), read_text(lot_file)))
        lot_data = load_json(lot_file)
    else:
        lot_data = None
    vec = VEC_DIR / f"{lot_id}.json"
    if vec.exists():
        files.append((str(vec), read_text(vec)))
    if not lot_data:
        return files
    lot = lot_data[0] if isinstance(lot_data, list) else lot_data
    raw_rel = lot.get("source:path")
    if raw_rel:
        raw_path = raw_post_path(raw_rel, RAW_DIR)
        files.append((str(raw_path), read_text(raw_path)))
    for rel in lot.get("files", []):
        p = MEDIA_DIR / rel
        files.append((str(p), f"<binary {p.name}>") if p.exists() else (str(p), ""))
        meta = p.with_suffix(".md")
        if meta.exists():
            files.append((str(meta), read_text(meta)))
        if has_caption(p):
            files.append((str(caption_json_path(p)), read_caption(p)))
    return files


def delete_files(lot_id: str) -> None:
    """Remove files related to ``lot_id`` from the filesystem."""
    lot_file = lot_json_path(lot_id, LOTS_DIR)
    lot_data = load_json(lot_file) if lot_file.exists() else None
    if lot_file.exists():
        lot_file.unlink()
    vec = VEC_DIR / f"{lot_id}.json"
    if vec.exists():
        vec.unlink()
    if not lot_data:
        return
    lot = lot_data[0] if isinstance(lot_data, list) else lot_data
    raw_rel = lot.get("source:path")
    if raw_rel:
        raw_path = raw_post_path(raw_rel, RAW_DIR)
        if raw_path.exists():
            raw_path.unlink()
    for rel in lot.get("files", []):
        p = MEDIA_DIR / rel
        for extra in [p, p.with_suffix(".md"), caption_json_path(p), caption_md_path(p)]:
            if extra.exists():
                extra.unlink()


def _message_reason(meta: dict, text: str) -> str | None:
    """Return explanation why a message would be skipped."""
    if meta.get("skipped_media"):
        return "skipped-media"
    if moderation.should_skip_user(meta.get("sender_username")):
        return "blacklisted-user"
    lower = text.lower()
    for phrase in moderation.BANNED_SUBSTRINGS:
        if phrase.lower() in lower:
            return f"banned phrase: {phrase}"
    files: list[str] = []
    if "files" in meta:
        val = meta.get("files")
        try:
            if isinstance(val, str):
                files = ast.literal_eval(val)
            elif isinstance(val, list):
                files = val
        except Exception:
            return "bad files list"
    if not text.strip() and not files:
        return "empty"
    return None


def _lot_reason(lot: dict) -> str | None:
    """Return explanation why ``lot`` would be skipped."""
    # Fraud reports are kept even when translations are missing so the check comes first.
    if lot.get("fraud") is not None:
        return "fraud"
    if lot.get("contact:telegram") == "@username":
        return "example contact"
    missing = [f for f in REVIEW_FIELDS if not lot.get(f)]
    if missing:
        return "missing translation"
    return None


def moderation_summary(lot_id: str) -> str:
    """Return a multi-line summary of moderation checks for ``lot_id``."""
    lines: list[str] = []
    lot_file = lot_json_path(lot_id, LOTS_DIR)
    lot_data = load_json(lot_file) if lot_file.exists() else None
    if lot_data:
        lots = lot_data if isinstance(lot_data, list) else [lot_data]
    else:
        lots = []
    raw_path = None
    if lots:
        raw_rel = lots[0].get("source:path")
        if raw_rel:
            raw_path = raw_post_path(raw_rel, RAW_DIR)
    if raw_path and raw_path.exists():
        meta, text = read_post(raw_path)
        reason = _message_reason(meta, text)
        lines.append("message: " + (reason or "ok"))
    else:
        lines.append("message: missing")
    for i, lot in enumerate(lots):
        reason = _lot_reason(lot)
        prefix = f"lot {i}" if len(lots) > 1 else "lot"
        lines.append(f"{prefix}: " + (reason or "ok"))
    if not lots:
        lines.append("lot: missing")

    vec_path = VEC_DIR / f"{lot_id}.json"
    if vec_path.exists():
        data = load_json(vec_path)
        if data is None:
            lines.append("vectors: corrupted")
        else:
            if isinstance(data, dict) and "id" in data:
                vec_count = 1
            elif isinstance(data, list):
                vec_count = len(data)
            else:
                vec_count = 0
            if vec_count and lots and vec_count != len(lots):
                lines.append(f"vectors: count mismatch {vec_count} vs {len(lots)}")
            else:
                lines.append("vectors: ok")
    else:
        lines.append("vectors: missing")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dump debug info for a lot")
    parser.add_argument("url", help="link to the lot page")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="drop existing files and refetch before dumping",
    )
    parser.add_argument(
        "--refetch",
        action="store_true",
        help="refetch from Telegram even when cached files are present",
    )
    args = parser.parse_args(argv)

    lot_id, _lang = parse_url(args.url)
    chat, mid = load_source_info(lot_id)
    if not chat or not mid:
        # When the lot file is missing try to recover the source directly from
        # the URL components. This allows fetching the Telegram post even when
        # the pipeline failed to persist JSON metadata.
        f_chat, f_mid = guess_source_from_lot(lot_id)
        if f_chat and f_mid:
            log.debug("Falling back to URL path", chat=f_chat, mid=f_mid)
            chat, mid = chat or f_chat, mid or f_mid
    if not chat or not mid:
        print("Failed to determine chat or message id", file=sys.stderr)
        return

    existing = collect_files(lot_id)
    if args.refresh:
        delete_files(lot_id)
        existing = []

    need_fetch = args.refetch or args.refresh or not existing

    if need_fetch:
        log.debug("Fetching from Telegram", chat=chat, mid=mid)
        logs = run_tg_fetch(chat, mid)
    else:
        log.debug("Using cached files", lot=lot_id)
        logs = "tg_client skipped, use --refetch to force"

    parts = ["### tg_client log", logs.strip()]
    parts.append("\n\n### moderation\n" + moderation_summary(lot_id))
    for name, content in collect_files(lot_id):
        parts.append(f"\n\n### {name}\n{content.strip()}")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
