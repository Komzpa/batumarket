from __future__ import annotations

"""Read and write raw Telegram posts stored as Markdown."""

from pathlib import Path

from log_utils import get_logger
from serde_utils import parse_md, write_md

log = get_logger().bind(module=__name__)


def read_post(path: Path) -> tuple[dict[str, str], str]:
    """Return metadata dictionary and body text for ``path``."""
    meta, text = parse_md(path)
    for k, v in list(meta.items()):
        if isinstance(v, str) and v.isdigit():
            meta[k] = int(v)
    return meta, text


def write_post(path: Path, meta: dict[str, str], body: str) -> None:
    """Write metadata and body as a Markdown post."""
    meta_lines = [f"{k}: {v}" for k, v in meta.items() if v is not None]
    write_md(path, "\n".join(meta_lines) + "\n\n" + body.strip())
    log.debug("Wrote post", path=str(path))

