from __future__ import annotations

from pathlib import Path

from log_utils import get_logger, install_excepthook
from oom_utils import prefer_oom_kill
from similar_utils import _load_embeddings, _sync_embeddings
from lot_io import iter_lot_files, read_lots
from price_utils import train_price_regression, save_price_model

log = get_logger().bind(script=__file__)
install_excepthook(log)
prefer_oom_kill()

LOTS_DIR = Path("data/lots")
MODEL_FILE = Path("data/price_model.json")


def _iter_lots() -> list[dict]:
    """Return all lots with generated ids."""
    lots: list[dict] = []
    for path in iter_lot_files(LOTS_DIR):
        data = read_lots(path)
        if not data:
            continue
        rel = path.relative_to(LOTS_DIR).with_suffix("")
        base = rel.name
        prefix = rel.parent
        for i, lot in enumerate(data):
            lid = str(prefix / f"{base}-{i}") if prefix.parts else f"{base}-{i}"
            lot["_id"] = lid
            lots.append(lot)
    log.info("Loaded lots", count=len(lots))
    return lots


def main() -> None:
    """Train price regression model and save it."""
    log.info("Training price model")
    embeds = _load_embeddings()
    lots = _iter_lots()
    lots, embeds = _sync_embeddings(lots, embeds)
    id_to_vec = {lot["_id"]: embeds.get(lot["_id"]) for lot in lots}
    model, cur_map, counts = train_price_regression(lots, id_to_vec)
    if model is None:
        log.error("No training samples")
        return
    save_price_model(model, cur_map, counts, MODEL_FILE)
    log.info("Price model saved", path=str(MODEL_FILE))


if __name__ == "__main__":
    main()
