#!/usr/bin/env python3
"""List images that need captions."""
from pathlib import Path
import sys

MEDIA_DIR = Path("data/media")
RAW_DIR = Path("data/raw")

# Make ``src`` imports work when executing this script directly from the
# repository root as done in the Makefile. Unit tests set ``PYTHONPATH``
# explicitly so this is only needed for manual runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from post_io import read_post
from image_io import read_image_meta
from caption_io import has_caption
from moderation import should_skip_message
from log_utils import get_logger
from oom_utils import prefer_oom_kill

log = get_logger().bind(script=__file__)


def _get_message_path(chat: str, msg_id: int) -> Path | None:
    """Return path of stored message ``msg_id`` in ``chat`` if any."""
    for p in (RAW_DIR / chat).rglob(f"{msg_id}.md"):
        return p
    return None


def main() -> None:
    prefer_oom_kill()
    files = sorted(
        (
            p
            for p in MEDIA_DIR.rglob("*")
            if p.is_file() and p.suffix not in {".md", ".json"}
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        if has_caption(path):
            continue
        meta = read_image_meta(path)
        chat = path.relative_to(MEDIA_DIR).parts[0]
        msg_id = meta.get("message_id")
        msg_path = None
        if msg_id:
            try:
                msg_path = _get_message_path(chat, int(msg_id))
            except Exception:
                log.debug("Bad message id", value=meta.get("message_id"), file=str(path))
        if msg_path and msg_path.exists():
            try:
                m_meta, text = read_post(msg_path)
                if should_skip_message(m_meta, text):
                    log.info("Skipping", file=str(path), reason="moderation")
                    continue
            except Exception:
                log.exception("Failed moderation check", file=str(path))
                continue
        sys.stdout.write(str(path))
        sys.stdout.write("\0")


if __name__ == "__main__":
    main()
