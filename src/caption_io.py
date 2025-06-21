"""Handle caption files stored beside images."""

from pathlib import Path

from serde_utils import read_md, write_md
from log_utils import get_logger

log = get_logger().bind(module=__name__)


def read_caption(path: Path) -> str:
    """Return caption text or empty string if missing."""
    return read_md(path)


def write_caption(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` with a trailing newline."""
    write_md(path, text)
    log.debug("Wrote caption", path=str(path))

