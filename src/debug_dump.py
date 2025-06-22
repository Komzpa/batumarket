#!/usr/bin/env python
"""Collect debug info for a single lot.

The script accepts a URL pointing to a generated HTML page and gathers
all related files for that lot. The Telegram client is invoked with
``--fetch`` so message metadata can be refreshed. Logs, lots, vectors and
raw posts are concatenated into a single output suitable for copy/paste
when troubleshooting the pipeline.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from caption_io import read_caption
from serde_utils import read_text, load_json
from log_utils import get_logger

log = get_logger().bind(script=__file__)

LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")
RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")


def parse_lot_id(url: str) -> tuple[str, str | None]:
    """Return ``(lot_id, lang)`` extracted from ``url``."""
    path = urlparse(url).path.lstrip("/")
    if path.endswith(".html"):
        path = path[:-5]
    if "_" in path:
        lot_id, lang = path.rsplit("_", 1)
    else:
        lot_id, lang = path, None
    return lot_id, lang


def load_source_info(lot_id: str) -> tuple[str | None, int | None]:
    """Return ``(chat, message_id)`` for ``lot_id`` if available."""
    lot_path = LOTS_DIR / f"{lot_id}.json"
    lot_data = load_json(lot_path)
    if not lot_data:
        log.warning("Lot file missing", lot=lot_id)
        return None, None
    lot = lot_data[0] if isinstance(lot_data, list) else lot_data
    chat = lot.get("source:chat")
    mid = lot.get("source:message_id")
    if (chat is None or mid is None) and lot.get("source:path"):
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
    if log_file.exists():
        output += "\n" + read_text(log_file)
        log_file.unlink()
    return output


def collect_files(lot_id: str) -> list[tuple[str, str]]:
    """Return ``[(name, content), ...]`` for files related to ``lot_id``."""
    files: list[tuple[str, str]] = []
    lot_file = LOTS_DIR / f"{lot_id}.json"
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
        raw_path = RAW_DIR / raw_rel
        files.append((str(raw_path), read_text(raw_path)))
    for rel in lot.get("files", []):
        p = MEDIA_DIR / rel
        files.append((str(p), f"<binary {p.name}>") if p.exists() else (str(p), ""))
        meta = p.with_suffix(".md")
        if meta.exists():
            files.append((str(meta), read_text(meta)))
        cap = p.with_suffix(".caption.md")
        if cap.exists():
            files.append((str(cap), read_caption(cap)))
    return files


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dump debug info for a lot")
    parser.add_argument("url", help="link to the lot page")
    args = parser.parse_args(argv)

    lot_id, _lang = parse_lot_id(args.url)
    chat, mid = load_source_info(lot_id)
    if not chat or not mid:
        print("Failed to determine chat or message id", file=sys.stderr)
        return

    logs = run_tg_fetch(chat, mid)
    parts = ["### tg_client log", logs.strip()]
    for name, content in collect_files(lot_id):
        parts.append(f"\n\n### {name}\n{content.strip()}")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
