from __future__ import annotations

"""Serialise and validate lot JSON files."""

from pathlib import Path
from typing import Iterable

from log_utils import get_logger
from serde_utils import load_json, write_json

log = get_logger().bind(module=__name__)


def read_lots(path: Path) -> list[dict] | None:
    """Return a list of lots from ``path`` or ``None`` when invalid."""
    data = load_json(path)
    if data is None:
        return None
    items = data if isinstance(data, list) else [data]
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            log.error("Lot is not dict", file=str(path))
            return None
        cleaned.append({k: v for k, v in item.items() if v not in ("", None, [])})
    return cleaned


def write_lots(path: Path, lots: Iterable[dict]) -> None:
    """Write lots to ``path`` using consistent JSON formatting."""
    write_json(path, list(lots))
    log.debug("Wrote lots", path=str(path))

