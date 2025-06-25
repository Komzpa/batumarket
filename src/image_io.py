"""Helpers for image metadata stored beside media files."""

from pathlib import Path

from notes_utils import write_md, parse_md
from log_utils import get_logger

log = get_logger().bind(module=__name__)


def read_image_meta(path: Path) -> dict[str, str]:
    """Return metadata from ``path.with_suffix('.md')``."""
    meta_path = path.with_suffix('.md')
    meta, _ = parse_md(meta_path)
    return meta


def write_image_meta(path: Path, meta: dict[str, str]) -> None:
    """Write ``meta`` to ``path.with_suffix('.md')``."""
    lines = [f"{k}: {v}" for k, v in meta.items() if v]
    write_md(path.with_suffix('.md'), "\n".join(lines))
    log.debug("Wrote image meta", path=str(path.with_suffix('.md')))

