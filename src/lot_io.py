from __future__ import annotations

"""Serialise and validate lot JSON files."""

from pathlib import Path
from typing import Iterable
from datetime import datetime, timezone

from log_utils import get_logger
from notes_utils import load_json, write_json

LOTS_DIR = Path("data/lots")
EMBED_DIR = Path("data/embeddings")

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

# ``title_<lang>`` and ``description_<lang>`` must be present for every lot.
TRANSLATION_FIELDS = [
    "title_en",
    "description_en",
    "title_ru",
    "description_ru",
    "title_ka",
    "description_ka",
]


def valid_lots(lots: list[dict] | None) -> bool:
    """Return ``True`` when every lot contains the required translations."""
    if lots is None:
        return False
    if not lots:
        return True
    for item in lots:
        if not isinstance(item, dict):
            return False
        if any(not item.get(f) for f in TRANSLATION_FIELDS):
            return False
    return True


def needs_cleanup(lots: list[dict]) -> bool:
    """Return ``True`` when ``clean_data`` would drop ``lots``."""
    missing = any(not lot.get(f) for lot in lots for f in TRANSLATION_FIELDS)
    flagged = any(lot.get("fraud") is not None for lot in lots)
    return missing and not flagged


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
        missing = [f for f in TRANSLATION_FIELDS if not lot.get(f)]
        assert not missing, f"missing translations: {', '.join(missing)}"
        cleaned.append(_clean_lot(lot))
    write_json(path, cleaned)
    log.debug("Wrote lots", path=str(path))


def make_lot_id(rel: Path, index: int) -> str:
    """Return lot id string for ``rel`` and ``index``.

    ``rel`` is the JSON file path relative to the ``data/lots`` directory
    without the ``.json`` suffix.
    """
    return f"{rel.with_suffix('')}-{index}"


def parse_lot_id(lot_id: str) -> tuple[Path, int]:
    """Return ``(relative_path, index)`` extracted from ``lot_id``."""
    p = Path(lot_id)
    name = p.name
    if '-' in name:
        base, idx = name.rsplit('-', 1)
    else:
        base, idx = name, '0'
    try:
        index = int(idx)
    except ValueError:
        index = 0
    return p.with_name(base), index


def lot_json_path(lot_id: str, root: Path) -> Path:
    """Return full JSON path for ``lot_id`` given ``root`` directory."""
    rel, _ = parse_lot_id(lot_id)
    return root / rel.with_suffix('.json')


def embedding_path(
    lot_path: Path, emb_root: Path = EMBED_DIR, lots_root: Path = LOTS_DIR
) -> Path:
    """Return embedding file path for ``lot_path``."""
    rel = lot_path.relative_to(lots_root)
    return (emb_root / rel).with_suffix(".json")


def iter_lot_files(root: Path = LOTS_DIR, newest_first: bool = False) -> list[Path]:
    """Return ``*.json`` files under ``root``.

    When ``newest_first`` is ``True`` the result is ordered by modification
    time with the most recently changed files first.  Both ``build_site.py`` and
    ``pending_embed.py`` rely on this helper so they scan the lot directory in
    the same order.
    """
    files = list(root.rglob("*.json"))
    if newest_first:
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        files.sort()
    return files


def get_lot(lot_id: str, root: Path = LOTS_DIR) -> dict | None:
    """Return the lot identified by ``lot_id`` or ``None`` when missing."""
    rel, idx = parse_lot_id(lot_id)
    path = root / rel.with_suffix(".json")
    data = read_lots(path)
    if not data or idx >= len(data) or idx < 0:
        return None
    return data[idx]

