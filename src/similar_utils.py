"""Utilities for handling lot embeddings and similar item cache."""

from __future__ import annotations

import math
from pathlib import Path

from serde_utils import load_json, write_json
from sklearn.neighbors import NearestNeighbors

from lot_io import LOTS_DIR, EMBED_DIR, lot_json_path
from log_utils import get_logger

log = get_logger().bind(module=__name__)

SIMILAR_DIR = Path("data/similar")


def _load_embeddings() -> dict[str, list[float]]:
    """Return mapping of lot id to embedding vector."""
    if not EMBED_DIR.exists():
        log.info("Embedding directory missing", path=str(EMBED_DIR))
        return {}
    data: dict[str, list[float]] = {}
    for path in EMBED_DIR.rglob("*.json"):
        obj = load_json(path)
        if isinstance(obj, dict) and "id" in obj and "vec" in obj:
            data[obj["id"]] = obj["vec"]
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and "id" in item and "vec" in item:
                    data[item["id"]] = item["vec"]
                else:
                    log.error("Bad embedding entry", file=str(path))
        else:
            log.error("Failed to parse embedding file", file=str(path))
    log.info("Loaded embeddings", count=len(data))
    return data


def _cos_sim(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two embeddings."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def _format_vector(vec: list[float] | None) -> str | None:
    """Return compact JSON representation for ``vec``."""
    if vec is None:
        return None
    parts = [f"{v:.4f}".rstrip("0").rstrip(".") for v in vec]
    return "[" + ",".join(parts) + "]"


def _similar_path(lot_path: Path) -> Path:
    """Return cache file path for ``lot_path`` under ``SIMILAR_DIR``."""
    rel = lot_path.relative_to(LOTS_DIR)
    return (SIMILAR_DIR / rel).with_suffix(".json")


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


def _save_similar(sim_map: dict[str, list[dict]]) -> None:
    """Write ``sim_map`` to ``SIMILAR_DIR`` mirroring ``LOTS_DIR`` layout."""
    files: dict[Path, list] = {}
    for lot_id, sims in sim_map.items():
        lot_path = lot_json_path(lot_id, LOTS_DIR)
        out = _similar_path(lot_path)
        files.setdefault(out, []).append({"id": lot_id, "similar": sims})
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
    """Fill ``sim_map`` for ``new_ids`` using a nearest neighbour search."""
    if not vec_ids:
        for lid in new_ids:
            sim_map[lid] = []
        return

    matrix = [id_to_vec[i] for i in vec_ids]
    k = min(7, len(matrix))
    nn = NearestNeighbors(n_neighbors=k, metric="cosine")
    nn.fit(matrix)
    index_map = {v: idx for idx, v in enumerate(vec_ids)}
    for lot_id in new_ids:
        idx = index_map.get(lot_id)
        if idx is None:
            sim_map[lot_id] = []
            continue
        dist, neigh = nn.kneighbors([matrix[idx]], n_neighbors=k)
        sims = []
        for d, other_idx in zip(dist[0][1:], neigh[0][1:]):
            other_id = vec_ids[other_idx]
            sims.append({"id": other_id, "dist": float(d)})
        sim_map[lot_id] = sims
        _update_reciprocal(sim_map, lot_id, sims)

