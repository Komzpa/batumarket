"""Predict prices for lots and cache the results."""

from __future__ import annotations

from pathlib import Path

from log_utils import get_logger, install_excepthook
from lot_io import iter_lot_files, read_lots
from post_io import RAW_DIR, read_post, raw_post_path
from moderation import should_skip_message, should_skip_lot
from similar_utils import _load_embeddings, _sync_embeddings
from notes_utils import write_json
from price_utils import apply_price_model, fetch_official_rates

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
PRICE_DIR = Path("data/prices")


def _price_path(lot_path: Path) -> Path:
    """Return cache file path for ``lot_path`` under ``PRICE_DIR``."""
    rel = lot_path.relative_to(LOTS_DIR)
    return (PRICE_DIR / rel).with_suffix(".json")


def _iter_lots() -> list[dict]:
    """Return lots filtered by moderation rules."""
    lots: list[dict] = []
    for path in iter_lot_files(LOTS_DIR):
        data = read_lots(path)
        if not data:
            continue
        rel = path.relative_to(LOTS_DIR).with_suffix("")
        base = rel.name
        prefix = rel.parent
        for i, lot in enumerate(data):
            src = lot.get("source:path")
            meta: dict[str, str] | None = None
            text = ""
            if src:
                raw_path = raw_post_path(src, RAW_DIR)
                meta, text = read_post(raw_path)
                if should_skip_message(meta, text):
                    continue
            if should_skip_lot(lot):
                continue
            lot["_file"] = path
            lot["_id"] = str(prefix / f"{base}-{i}") if prefix.parts else f"{base}-{i}"
            lots.append(lot)
    log.info("Loaded lots", count=len(lots))
    return lots


def _save_prices(lots: list[dict]) -> None:
    """Write ``ai_price`` and currency info next to ``LOTS_DIR``."""
    files: dict[Path, list] = {}
    for lot in lots:
        out = _price_path(lot["_file"])
        entry: dict[str, object] = {"id": lot["_id"]}
        if lot.get("ai_price") is not None:
            entry["ai_price"] = lot["ai_price"]
        if lot.get("price:currency") is not None:
            entry["price:currency"] = lot["price:currency"]
        files.setdefault(out, []).append(entry)
    for path, items in files.items():
        write_json(path, items)


def main() -> None:
    """Update ``data/prices`` with predictions derived from embeddings."""
    log.info("Computing prices")
    embeddings = _load_embeddings()
    lots = _iter_lots()
    lots, embeddings = _sync_embeddings(lots, embeddings)
    id_to_vec = {lot["_id"]: embeddings.get(lot["_id"]) for lot in lots}

    rates_official = fetch_official_rates()
    ai_rates = apply_price_model(lots, id_to_vec, rates_official)

    _save_prices(lots)
    write_json(PRICE_DIR / "rates.json", ai_rates)
    log.info("Price cache updated")


if __name__ == "__main__":
    main()
