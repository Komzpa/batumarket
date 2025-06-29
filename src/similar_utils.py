"""Utilities for handling lot embeddings and similar item cache."""

from __future__ import annotations

import math
from pathlib import Path

import progressbar
import numpy as np

from notes_utils import load_json, write_json
from sklearn.neighbors import NearestNeighbors

from lot_io import LOTS_DIR, EMBED_DIR, lot_json_path
from log_utils import get_logger

log = get_logger().bind(module=__name__)

SIMILAR_DIR = Path("data/similar")
MORE_USER_DIR = Path("data/more_user")


def _load_embeddings() -> dict[str, np.ndarray]:
    """Return mapping of lot id to embedding vector.

    Vectors are stored as ``numpy.float16`` arrays which halves the
    memory footprint compared to ``float32`` and drastically reduces
    memory usage compared to plain Python lists.
    """
    if not EMBED_DIR.exists():
        log.info("Embedding directory missing", path=str(EMBED_DIR))
        return {}
    data: dict[str, np.ndarray] = {}
    for path in EMBED_DIR.rglob("*.json"):
        obj = load_json(path)
        if isinstance(obj, dict) and "id" in obj and "vec" in obj:
            data[obj["id"]] = np.asarray(obj["vec"], dtype=np.float16)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and "id" in item and "vec" in item:
                    data[item["id"]] = np.asarray(item["vec"], dtype=np.float16)
                else:
                    log.error("Bad embedding entry", file=str(path))
        else:
            log.error("Failed to parse embedding file", file=str(path))
    log.info("Loaded embeddings", count=len(data))
    return data


def _cos_sim(a: "list[float] | np.ndarray", b: "list[float] | np.ndarray") -> float:
    """Return cosine similarity between two embeddings."""
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return -1.0
    dot = float(np.dot(va, vb))
    return dot / (na * nb)


def _format_vector(vec: "list[float] | np.ndarray | None") -> str | None:
    """Return compact JSON representation for ``vec``."""
    if vec is None:
        return None
    if isinstance(vec, np.ndarray):
        values = vec.tolist()
    else:
        values = list(vec)
    parts = [f"{v:.4f}".rstrip("0").rstrip(".") for v in values]
    return "[" + ",".join(parts) + "]"


def _similar_path(lot_path: Path) -> Path:
    """Return cache file path for ``lot_path`` under ``SIMILAR_DIR``."""
    rel = lot_path.relative_to(LOTS_DIR)
    return (SIMILAR_DIR / rel).with_suffix(".json")


def _more_user_path(lot_path: Path) -> Path:
    """Return cache file path for ``lot_path`` under ``MORE_USER_DIR``."""
    rel = lot_path.relative_to(LOTS_DIR)
    return (MORE_USER_DIR / rel).with_suffix(".json")


def _load_similar() -> dict[str, list[dict]]:
    """Return cached similar lots mapping."""
    if not SIMILAR_DIR.exists():
        return {}
    data: dict[str, list[dict]] = {}
    for path in SIMILAR_DIR.rglob("*.json"):
        obj = load_json(path)
        if isinstance(obj, list):
            for item in obj:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("similar"), list)
                ):
                    sims = []
                    for s in item["similar"]:
                        if (
                            isinstance(s, dict)
                            and isinstance(s.get("id"), str)
                            and isinstance(s.get("dist"), (int, float))
                        ):
                            sims.append({"id": s["id"], "dist": float(s["dist"])} )
                    if len(sims) == len(item["similar"]):
                        data[item["id"]] = sims
    if data:
        log.info("Loaded similar cache", count=len(data))
    return data


def _load_more_user() -> dict[str, list[dict]]:
    """Return cached per-user lot mapping."""
    if not MORE_USER_DIR.exists():
        return {}
    data: dict[str, list[dict]] = {}
    for path in MORE_USER_DIR.rglob("*.json"):
        obj = load_json(path)
        if isinstance(obj, list):
            for item in obj:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("more_user"), list)
                ):
                    sims = []
                    for s in item["more_user"]:
                        if isinstance(s, dict) and isinstance(s.get("id"), str):
                            sims.append({"id": s["id"]})
                    if len(sims) == len(item["more_user"]):
                        data[item["id"]] = sims
    if data:
        log.info("Loaded user cache", count=len(data))
    return data


def _save_similar(sim_map: dict[str, list[dict]]) -> None:
    """Write ``sim_map`` to ``SIMILAR_DIR`` mirroring ``LOTS_DIR`` layout."""
    files: dict[Path, list] = {}
    for lot_id, sims in sim_map.items():
        lot_path = lot_json_path(lot_id, LOTS_DIR)
        out = _similar_path(lot_path)
        files.setdefault(out, []).append({"id": lot_id, "similar": sims})
    for path, items in files.items():
        write_json(path, items)


def _save_more_user(more_map: dict[str, list[dict]]) -> None:
    """Write ``more_map`` to ``MORE_USER_DIR`` mirroring ``LOTS_DIR`` layout."""
    files: dict[Path, list] = {}
    for lot_id, sims in more_map.items():
        lot_path = lot_json_path(lot_id, LOTS_DIR)
        out = _more_user_path(lot_path)
        files.setdefault(out, []).append({"id": lot_id, "more_user": sims})
    for path, items in files.items():
        write_json(path, items)


def _update_reciprocal(sim_map: dict[str, list[dict]], lot_id: str, sims: list[dict]) -> None:
    """Insert ``lot_id`` into caches of lots listed in ``sims`` if closer."""
    for entry in sims:
        other = entry["id"]
        dist = entry["dist"]
        items = sim_map.setdefault(other, [])
        found = False
        for item in items:
            if item["id"] == lot_id:
                item["dist"] = dist
                found = True
                break
        if not found:
            items.append({"id": lot_id, "dist": dist})
        items.sort(key=lambda x: x["dist"])
        if len(items) > 6:
            del items[6:]


def _prune_similar(sim_map: dict[str, list[dict]], valid_ids: set[str]) -> None:
    """Drop cache entries referring to ids not in ``valid_ids``."""
    removed = set(sim_map) - valid_ids
    for key in removed:
        sim_map.pop(key, None)
    for items in sim_map.values():
        items[:] = [i for i in items if i.get("id") in valid_ids]


def _calc_similar_nn(
    sim_map: dict[str, list[dict]],
    new_ids: list[str],
    vec_ids: list[str],
    id_to_vec: dict[str, list[float]],
) -> None:
    """Fill ``sim_map`` for ``new_ids`` using a nearest neighbour search.

    ``vec_ids`` lists all lots that have an embedding.  ``new_ids`` is a subset
    for which we still need recommendations.  We gather vectors for
    ``vec_ids`` and use ``NearestNeighbors`` from scikit-learn to find the
    closest items.  Embeddings of lots without a vector are skipped.
    """
    if not vec_ids:
        for lid in new_ids:
            sim_map[lid] = []
        return

    # Convert embedding map to a list so we can build a contiguous matrix for
    # scikit-learn.  ``vec_ids`` preserve the order of vectors in this matrix.
    matrix = [id_to_vec[i] for i in vec_ids]
    k = min(7, len(matrix))

    # Fit nearest neighbours on the full matrix once.
    nn = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn.fit(matrix)

    # Map each lot id to its row index to quickly look up vectors.
    index_map = {v: idx for idx, v in enumerate(vec_ids)}

    # Build a batch of vectors to query at once.  Lots missing an embedding get
    # an empty result immediately.
    queries = []
    q_ids = []
    for lid in new_ids:
        idx = index_map.get(lid)
        if idx is not None:
            queries.append(matrix[idx])
            q_ids.append(lid)
        else:
            sim_map[lid] = []

    if not queries:
        return

    # Find neighbours for all queries in a single call which is much faster than
    # querying one by one.
    dist, neigh = nn.kneighbors(queries, n_neighbors=k)

    # ``progressbar2`` changed the ``maxval`` argument to ``max_value`` in newer
    # releases.  Handle both so we work across distributions.
    widgets = [
        "similar ",
        progressbar.Bar(marker="#", left="[", right="]"),
        " ",
        progressbar.ETA(),
    ]
    try:
        bar = progressbar.ProgressBar(max_value=len(q_ids), widgets=widgets)
    except TypeError as exc:
        if "max_value" in str(exc) and "maxval" in str(exc):
            bar = progressbar.ProgressBar(maxval=len(q_ids), widgets=widgets)
        else:
            raise
    bar.start()
    for i, lot_id in enumerate(q_ids):
        # Skip the first neighbour which is the query item itself.
        sims = []
        for d, other_idx in zip(dist[i][1:], neigh[i][1:]):
            other_id = vec_ids[other_idx]
            sims.append({"id": other_id, "dist": float(d)})
        sim_map[lot_id] = sims
        _update_reciprocal(sim_map, lot_id, sims)
        bar.update(i + 1)
    bar.finish()


def _sync_embeddings(
    lots: list[dict],
    embeddings: dict[str, list[float]],
) -> tuple[list[dict], dict[str, list[float]]]:
    """Drop lots or vectors that do not match and return cleaned data."""
    lot_keys = {lot["_id"] for lot in lots}
    emb_keys = set(embeddings)
    extra_embs = emb_keys - lot_keys
    if extra_embs:
        for key in extra_embs:
            embeddings.pop(key, None)
        log.debug("Dropped embeddings without lots", count=len(extra_embs))
    missing_embs = lot_keys - emb_keys
    if missing_embs:
        lots = [lot for lot in lots if lot["_id"] not in missing_embs]
        log.debug("Dropped lots without embeddings", count=len(missing_embs))
    return lots, embeddings


def _similar_by_user(
    lots: list[dict], id_to_vec: dict[str, list[float]]
) -> dict[str, list[dict]]:
    """Return map of lot id to other lots from the same user."""
    user_map: dict[str, list[dict]] = {}
    for lot in lots:
        user = (
            lot.get("contact:telegram")
            or lot.get("source:author:telegram")
            or lot.get("source:author:name")
        )
        if isinstance(user, list):
            log.debug("Multiple telegram users", id=lot.get("_id"), value=user)
            user = user[0] if user else None
        if user is not None:
            user_map.setdefault(str(user), []).append(lot)

    more_user_map: dict[str, list[dict]] = {}
    for user, user_lots in user_map.items():
        ids = [lot["_id"] for lot in user_lots]
        matrix = [id_to_vec[i] for i in ids if id_to_vec.get(i)]
        if len(matrix) < 2:
            for lid in ids:
                more_user_map[lid] = []
            continue

        k = min(len(matrix), 21)
        nn = NearestNeighbors(n_neighbors=k, metric="cosine")
        nn.fit(matrix)
        dist, neigh = nn.kneighbors(matrix, n_neighbors=k)

        for i, lid in enumerate(ids[: len(matrix)]):
            sims = []
            for other_idx in neigh[i][1:]:
                other_id = ids[other_idx]
                sims.append({"id": other_id})
            more_user_map[lid] = sims[:20]
    return more_user_map

