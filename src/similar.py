"""Calculate similarity recommendations for all lots."""

from __future__ import annotations

from pathlib import Path

from log_utils import get_logger, install_excepthook
from lot_io import iter_lot_files, read_lots
from post_io import RAW_DIR, read_post, raw_post_path
from moderation import should_skip_message, should_skip_lot
from similar_utils import (
    _load_embeddings,
    _load_similar,
    _save_similar,
    _load_more_user,
    _save_more_user,
    _prune_similar,
    _calc_similar_nn,
    _sync_embeddings,
    _similar_by_user,
)

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")


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
            lot["_id"] = str(prefix / f"{base}-{i}") if prefix.parts else f"{base}-{i}"
            lots.append(lot)
    log.info("Loaded lots", count=len(lots))
    return lots


def main() -> None:
    """Update ``data/similar`` using available embeddings."""
    log.info("Computing similar lots")
    embeddings = _load_embeddings()
    lots = _iter_lots()
    sim_map = _load_similar()

    lots, embeddings = _sync_embeddings(lots, embeddings)
    id_to_vec = {lot["_id"]: embeddings.get(lot["_id"]) for lot in lots}
    lot_keys = {lot["_id"] for lot in lots}
    _prune_similar(sim_map, lot_keys)
    new_ids = [i for i in lot_keys if i not in sim_map]
    vec_ids = [i for i in lot_keys if id_to_vec.get(i)]
    _calc_similar_nn(sim_map, new_ids, vec_ids, id_to_vec)

    more_user_map = _similar_by_user(lots, id_to_vec)

    _save_similar(sim_map)
    _save_more_user(more_user_map)
    log.info("Similar cache updated")


if __name__ == "__main__":
    main()
