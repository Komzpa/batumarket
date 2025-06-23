"""Utilities for handling raw message files."""

from __future__ import annotations

import ast
from pathlib import Path

from log_utils import get_logger
from post_io import read_post
from caption_io import read_caption

log = get_logger().bind(module=__name__)




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
    meta, text = read_post(msg_path)
    files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
    captions = []
    for rel in files:
        cap_path = media_dir / rel
        caption_text = read_caption(cap_path)
        captions.append(caption_text)
    prompt = build_prompt(text, files, captions)
    log.debug("Built parser input", path=str(msg_path))
    return prompt
