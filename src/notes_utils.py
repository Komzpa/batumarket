"""Helpers for reading and writing Markdown files."""

from __future__ import annotations

import json
from pathlib import Path

from log_utils import get_logger

log = get_logger().bind(module=__name__)


def read_text(path: str | Path) -> str:
    """Return file contents as UTF-8 or empty string when missing."""
    p = Path(path)
    if not p.exists():
        log.debug("read_text missing", path=str(p))
        return ""
    return p.read_text(encoding="utf-8")


def read_md(path: str | Path) -> str:
    """Alias for :func:`read_text` used for Markdown files."""
    return read_text(path)


def write_md(path: str | Path, text: str) -> None:
    """Write ``text`` to ``path`` ensuring a trailing newline."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text, encoding="utf-8")
    log.debug("Wrote markdown", path=str(p))


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


def parse_md(path: Path) -> tuple[dict[str, str], str]:
    """Return metadata dictionary and body text from ``path``."""
    text = read_md(path)
    return _parse_block(text)


def load_json(path: Path):
    """Return parsed JSON or ``None`` when invalid."""
    if not path.exists():
        log.warning("File not found", path=str(path))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to parse JSON", file=str(path))
        return None


def write_json(path: Path, data) -> None:
    """Serialise ``data`` to ``path`` with standard options."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.debug("Wrote JSON", path=str(path))
