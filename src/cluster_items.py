from __future__ import annotations

from pathlib import Path
from collections import defaultdict
from typing import Iterable

from log_utils import get_logger, install_excepthook
from oom_utils import prefer_oom_kill
from lot_io import iter_lot_files, read_lots
from similar_utils import _load_embeddings, _sync_embeddings, _cos_sim
from notes_utils import write_json

from sklearn.cluster import KMeans

log = get_logger().bind(script=__file__)

LOTS_DIR = Path("data/lots")
OUTPUT_FILE = Path("data/item_clusters.json")


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
            lot["_id"] = str(prefix / f"{base}-{i}") if prefix.parts else f"{base}-{i}"
            lots.append(lot)
    log.info("Loaded lots", count=len(lots))
    return lots


def collect_clusters() -> dict[str, list[str]]:
    """Return mapping of cluster name to lot ids."""
    log.debug("Loading embeddings")
    embeds = _load_embeddings()
    log.debug("Loading lots")
    lots = _iter_lots()
    lots, embeds = _sync_embeddings(lots, embeds)
    id_to_vec = {lot["_id"]: embeds.get(lot["_id"]) for lot in lots}

    items: list[tuple[str, str, list[float]]] = []
    for lot in lots:
        if lot.get("market:deal") != "sell_item":
            continue
        itype = lot.get("item:type")
        if isinstance(itype, list):
            itype = itype[0] if itype else None
        if not isinstance(itype, str) or not itype:
            continue
        vec = id_to_vec.get(lot["_id"])
        if vec is None:
            continue
        items.append((lot["_id"], itype, vec))

    if not items:
        return {}

    vectors = [it[2] for it in items]
    n_clusters = max(1, round(len(items) / 30))
    n_clusters = min(n_clusters, len(items))
    km = KMeans(n_clusters=n_clusters, n_init="auto", random_state=0)
    labels = km.fit_predict(vectors)

    grouped: dict[int, list[tuple[str, str, list[float]]]] = defaultdict(list)
    for lab, item in zip(labels, items):
        grouped[int(lab)].append(item)

    result: dict[str, list[str]] = {}
    for items in grouped.values():
        dims = len(items[0][2])
        centroid = [0.0] * dims
        for _, _, vec in items:
            for i, v in enumerate(vec):
                centroid[i] += v
        centroid = [v / len(items) for v in centroid]

        type_vecs: dict[str, list[list[float]]] = defaultdict(list)
        for lid, itype, vec in items:
            type_vecs[itype].append(vec)

        scores = []
        for itype, vecs in type_vecs.items():
            mean = [sum(v[i] for v in vecs) / len(vecs) for i in range(dims)]
            sim = _cos_sim(mean, centroid)
            scores.append((sim, itype))
        scores.sort(reverse=True)
        name = " ".join(t for _, t in scores)
        result[name] = [lid for lid, _, _ in items]

    return result


def main() -> None:
    """Cluster items and save the result."""
    install_excepthook(log)
    prefer_oom_kill()
    log.info("Clustering items")
    clusters = collect_clusters()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_FILE, clusters)
    log.info("Wrote clusters", path=str(OUTPUT_FILE), count=len(clusters))


if __name__ == "__main__":
    main()
