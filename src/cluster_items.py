from __future__ import annotations

from pathlib import Path
from collections import defaultdict
from typing import Iterable

import numpy as np

from log_utils import get_logger, install_excepthook
from oom_utils import prefer_oom_kill
from lot_io import iter_lot_files, read_lots, make_lot_id, embedding_path
from similar_utils import _cos_sim
from notes_utils import write_json, load_json

from sklearn.cluster import MiniBatchKMeans

log = get_logger().bind(script=__file__)

LOTS_DIR = Path("data/lots")
OUTPUT_FILE = Path("data/item_clusters.json")


def _iter_items() -> Iterable[tuple[str, str, np.ndarray]]:
    """Yield ``(id, item:type, embedding)`` for ``sell_item`` lots.

    Embeddings are loaded on demand so memory usage stays minimal.
    """
    for path in iter_lot_files(LOTS_DIR):
        lots = read_lots(path)
        if not lots:
            continue
        rel = path.relative_to(LOTS_DIR)
        epath = embedding_path(path)
        embeds = load_json(epath) or []
        embed_map = {}
        if isinstance(embeds, dict) and "id" in embeds and "vec" in embeds:
            embed_map[str(embeds["id"])] = np.asarray(embeds["vec"], dtype=np.float32)
        elif isinstance(embeds, list):
            for item in embeds:
                if isinstance(item, dict) and "id" in item and "vec" in item:
                    embed_map[str(item["id"])] = np.asarray(item["vec"], dtype=np.float32)
        for idx, lot in enumerate(lots):
            if lot.get("market:deal") != "sell_item":
                continue
            itype = lot.get("item:type")
            if isinstance(itype, list):
                itype = itype[0] if itype else None
            if not isinstance(itype, str) or not itype:
                continue
            lot_id = make_lot_id(rel, idx)
            vec = embed_map.get(lot_id)
            if vec is None:
                continue
            yield lot_id, itype, vec


def collect_clusters(batch_size: int = 256) -> dict[str, list[str]]:
    """Return mapping of cluster name to lot ids.

    ``MiniBatchKMeans`` processes item embeddings in chunks so only a
    small batch resides in memory at a time.  Initial centroids come from
    the most common ``item:type`` values so existing categories guide the
    clustering.
    """

    log.debug("Counting items")
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for _, itype, _ in _iter_items():
        counts[itype] += 1
        total += 1
    if total == 0:
        return {}

    n_clusters = max(1, round(total / 30))
    n_clusters = min(n_clusters, total)

    top_types = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n_clusters]
    top_set = {t for t, _ in top_types}
    centers: list[np.ndarray] | None = None
    if len(top_types) >= n_clusters:
        dim = None
        sums: dict[str, np.ndarray] = {}
        for _, itype, vec in _iter_items():
            if itype not in top_set:
                continue
            if dim is None:
                dim = len(vec)
                for t in top_set:
                    sums[t] = np.zeros(dim, dtype=np.float32)
            sums[itype] += vec
        centers = [sums[t] / counts[t] for t, _ in top_types]

    if centers is not None:
        init = np.stack(centers)
        km = MiniBatchKMeans(
            n_clusters=n_clusters,
            init=init,
            n_init=1,
            random_state=0,
            batch_size=batch_size,
        )
    else:
        km = MiniBatchKMeans(n_clusters=n_clusters, random_state=0, batch_size=batch_size)

    log.debug("Fitting clusters", count=total, clusters=n_clusters)
    batch: list[np.ndarray] = []
    for _, _, vec in _iter_items():
        batch.append(vec)
        if len(batch) >= batch_size:
            km.partial_fit(batch)
            batch.clear()
    if batch:
        km.partial_fit(batch)

    log.debug("Assigning labels")
    grouped: dict[int, dict[str, list]] = {}
    for lid, itype, vec in _iter_items():
        lab = int(km.predict([vec])[0])
        info = grouped.setdefault(lab, {"ids": [], "sum": np.zeros(len(vec)), "type_vecs": defaultdict(list)})
        info["ids"].append(lid)
        info["sum"] += vec
        info["type_vecs"][itype].append(vec)

    result: dict[str, list[str]] = {}
    for info in grouped.values():
        centroid = info["sum"] / len(info["ids"])
        scores = []
        for itype, vecs in info["type_vecs"].items():
            mean = np.mean(vecs, axis=0)
            sim = _cos_sim(mean, centroid)
            scores.append((sim, itype))
        scores.sort(reverse=True)
        name = " ".join(t for _, t in scores)
        result[name] = info["ids"]

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
