from __future__ import annotations

from pathlib import Path
from collections import defaultdict
from typing import Iterable, Dict

import math
import numpy as np

from log_utils import get_logger, install_excepthook
from oom_utils import prefer_oom_kill
from lot_io import iter_lot_files, read_lots, make_lot_id, embedding_path
from similar_utils import _cos_sim
from notes_utils import write_json, load_json

from sklearn.cluster import KMeans

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


def _collect_category_vectors() -> Dict[str, np.ndarray]:
    """Return mean embedding for every ``item:type``.

    Embeddings are streamed from disk so memory use stays manageable.
    """
    sums: Dict[str, np.ndarray] = {}
    counts: Dict[str, int] = defaultdict(int)
    for _, itype, vec in _iter_items():
        if itype not in sums:
            sums[itype] = np.zeros(len(vec), dtype=np.float32)
        sums[itype] += vec
        counts[itype] += 1
    return {t: sums[t] / counts[t] for t in sums}


def collect_clusters() -> dict[str, list[str]]:
    """Return mapping of cluster name to ``item:type`` values.

    Category embeddings are averaged first so clustering deals with a
    manageable number of vectors. The number of clusters follows the
    square root heuristic.
    """

    cat_vecs = _collect_category_vectors()
    if not cat_vecs:
        return {}

    types = list(cat_vecs.keys())
    vectors = np.stack([cat_vecs[t] for t in types])

    n_clusters = max(1, round(math.sqrt(len(types))))

    counts = {t: 0 for t in types}
    for _, itype, _ in _iter_items():
        counts[itype] += 1

    top_types = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n_clusters]
    centers = np.stack([cat_vecs[t] for t, _ in top_types]) if len(top_types) >= n_clusters else None

    if centers is not None:
        km = KMeans(n_clusters=n_clusters, init=centers, n_init=1, random_state=0)
    else:
        km = KMeans(n_clusters=n_clusters, random_state=0)

    log.debug("Fitting category clusters", count=len(types), clusters=n_clusters)
    km.fit(vectors)

    grouped: Dict[int, list[str]] = defaultdict(list)
    for t, lab in zip(types, km.labels_):
        grouped[int(lab)].append(t)

    result: dict[str, list[str]] = {}
    for lab, names in grouped.items():
        centroid = km.cluster_centers_[lab]
        scores = []
        for t in names:
            sim = _cos_sim(cat_vecs[t], centroid)
            scores.append((sim, t))
        scores.sort(reverse=True)
        cname = " ".join(t for _, t in scores)
        result[cname] = names

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
