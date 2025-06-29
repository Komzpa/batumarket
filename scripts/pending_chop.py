#!/usr/bin/env python3
"""List message files needing chopping.

Outputs NUL-separated paths sorted by modification time descending.
"""

from pathlib import Path
import sys
# Make ``src`` imports work when executing this script directly from the
# repository root as done in the Makefile.  Unit tests set ``PYTHONPATH``
# explicitly so this is only needed for manual runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from log_utils import get_logger
from oom_utils import prefer_oom_kill
from post_io import read_post
from moderation import should_skip_message

log = get_logger().bind(script=__file__)

RAW_DIR = Path("data/raw")
LOTS_DIR = Path("data/lots")


def main() -> None:
    prefer_oom_kill()
    files = sorted(
        RAW_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for msg in files:
        rel = msg.relative_to(RAW_DIR)
        out = LOTS_DIR / rel.with_suffix(".json")
        if out.exists():
            continue
        try:
            meta, text = read_post(msg)
        except Exception:
            log.exception("Failed to read post", path=str(msg))
            continue
        if should_skip_message(meta, text):
            log.info("Skipping", path=str(msg), reason="moderation")
            continue
        sys.stdout.write(str(msg))
        sys.stdout.write("\0")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
