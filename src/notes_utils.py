"""Small helper functions to read and write markdown files."""

"""Compatibility wrappers around :mod:`serde_utils` for notes."""

from pathlib import Path

from log_utils import get_logger
from serde_utils import read_md, read_text, write_md

log = get_logger().bind(module=__name__)


def collect_notes() -> str:
    """Return combined notes if ``notes/`` exists."""
    notes_dir = Path("notes")
    if not notes_dir.exists():
        return ""
    parts = []
    for f in sorted(notes_dir.glob("*.md")):
        parts.append(read_md(f))
    return "\n\n".join(parts)
