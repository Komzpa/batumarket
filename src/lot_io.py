from __future__ import annotations

"""Serialise and validate lot JSON files."""

from pathlib import Path
from typing import Iterable
from datetime import datetime, timezone

from log_utils import get_logger
from serde_utils import load_json, write_json

log = get_logger().bind(module=__name__)


def _clean_lot(lot: dict) -> dict:
    """Return ``lot`` without empty or null fields."""
    return {k: v for k, v in lot.items() if v not in ("", None, [])}


SELLER_FIELDS = [
    "contact:phone",
    "contact:telegram",
    "contact:instagram",
    "contact:viber",
    "contact:whatsapp",
    "source:author:telegram",
    "source:author:name",
    "seller",
]


def get_seller(lot: dict) -> str | None:
    """Return the seller identifier or ``None`` when missing."""
    for key in SELLER_FIELDS:
        value = lot.get(key)
        if isinstance(value, list):
            # Older lots might contain lists for contact fields. Use the first
            # entry so the site and ontology stay consistent.
            value = value[0] if value else None
        if value:
            return str(value)
    return None


def get_timestamp(lot: dict) -> datetime | None:
    """Return ``lot['timestamp']`` as a timezone-aware ``datetime``."""
    ts = lot.get("timestamp")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except Exception:
        log.debug("Bad timestamp", value=ts, id=lot.get("_id"))
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if dt > now:
        log.debug("Future timestamp", value=ts, id=lot.get("_id"))
        return None
    return dt


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
        cleaned.append(_clean_lot(item))
    return cleaned


def write_lots(path: Path, lots: Iterable[dict]) -> None:
    """Write lots to ``path`` using consistent JSON formatting."""
    cleaned = []
    for lot in lots:
        assert get_timestamp(lot) is not None, "timestamp required"
        assert get_seller(lot) is not None, "seller required"
        cleaned.append(_clean_lot(lot))
    write_json(path, cleaned)
    log.debug("Wrote lots", path=str(path))

