"""Utilities for handling raw message files."""

from __future__ import annotations

import ast
from pathlib import Path

from log_utils import get_logger
from notes_utils import read_md

log = get_logger().bind(module=__name__)


def parse_md(path: Path) -> tuple[dict[str, str], str]:
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


def build_prompt(text: str, files: list[str], captions: list[str]) -> str:
    """Return prompt combining message text with captioned file names."""
    parts = []
    if text.strip():
        parts.append(f"Message text:\n{text.strip()}")
    for file, caption in zip(files, captions):
        parts.append(f"Image {file}:\n{caption.strip()}")
    return "\n\n".join(parts)


def gather_chop_input(msg_path: Path, media_dir: Path) -> str:
    """Return the exact text fed to the lot parser for ``msg_path``."""
    meta, text = parse_md(msg_path)
    files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
    captions = []
    for rel in files:
        cap_path = (media_dir / rel).with_suffix(".caption.md")
        caption_text = read_md(str(cap_path))
        captions.append(caption_text)
    prompt = build_prompt(text, files, captions)
    log.debug("Built parser input", path=str(msg_path))
    return prompt
