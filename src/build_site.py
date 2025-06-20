"""Render static HTML pages from JSON lots using Jinja2.

Each ``*.json`` file under ``data/lots`` may contain several lots so we assign
a unique ``_page_id`` to every entry.  Templates live in ``templates/`` and the
output is written to ``data/views`` keeping the directory layout intact.  The
script also loads ``data/vectors.jsonl`` if present to find similar lots based
on cosine similarity.  ``data/ontology.json`` is consulted to display table
columns in a stable order.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader

from config_utils import load_config
from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
VIEWS_DIR = Path("data/views")
TEMPLATES = Path("templates")
VEC_DIR = Path("data/vectors")
ONTOLOGY = Path("data/ontology.json")


def _lot_id_for(path: Path) -> str:
    """Return unique id ``chat/msg_id`` for ``path``."""
    rel = path.relative_to(LOTS_DIR)
    chat = rel.parts[0]
    return f"{chat}/{path.stem}"


def _load_vectors() -> dict[str, list[float]]:
    """Return mapping of lot id to embedding vector."""
    if not VEC_DIR.exists():
        log.info("Vector directory missing", path=str(VEC_DIR))
        return {}
    data: dict[str, list[float]] = {}
    for path in VEC_DIR.rglob("*.json"):
        try:
            obj = json.loads(path.read_text())
            data[obj["id"]] = obj["vec"]
        except Exception:
            log.exception("Failed to parse vector file", file=str(path))
    log.info("Loaded vectors", count=len(data))
    return data


def _cos_sim(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def _load_ontology() -> list[str]:
    if not ONTOLOGY.exists():
        return []
    try:
        data = json.loads(ONTOLOGY.read_text())
    except Exception:
        log.exception("Bad ontology", path=str(ONTOLOGY))
        return []
    return sorted(data.keys())


def _iter_lots() -> list[dict]:
    """Yield lots with helper metadata."""
    lots = []
    for path in LOTS_DIR.rglob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            log.exception("Failed to parse lot file", file=str(path))
            continue
        if isinstance(data, dict):
            data = [data]
        base = path.stem
        for i, lot in enumerate(data):
            lot["_file"] = path
            lot["_id"] = f"{base}-{i}"
            lots.append(lot)
    log.info("Loaded lots", count=len(lots))
    return lots


def build_page(env: Environment, lot: dict, similar: list[dict], fields: list[str], langs: list[str]) -> None:
    images = []
    for rel in lot.get("files", []):
        p = Path("data/media") / rel
        cap = p.with_suffix(".caption.md")
        captions = {}
        for lang in langs:
            captions[lang] = cap.read_text(encoding="utf-8") if cap.exists() else ""
        images.append({"path": rel, "caption": captions})

    attrs = {k: v for k, v in lot.items() if k not in {"files"} and not k.startswith("title_") and not k.startswith("description_")}
    sorted_attrs = {k: attrs[k] for k in fields if k in attrs}
    for k in attrs:
        if k not in sorted_attrs:
            sorted_attrs[k] = attrs[k]

    chat = lot.get("source:chat")
    mid = lot.get("source:message_id")
    tg_link = f"https://t.me/{chat}/{mid}" if chat and mid else ""

    template = env.get_template("lot.html")
    out = VIEWS_DIR / f"{lot['_id']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        template.render(
            title=lot.get("title_en", "Lot"),
            lot=lot,
            images=images,
            attrs=sorted_attrs,
            tg_link=tg_link,
            similar=similar,
            langs=langs,
        )
    )
    log.debug("Wrote", path=str(out))


def main() -> None:
    log.info("Building site")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    cfg = load_config()
    langs = getattr(cfg, "LANGS", ["en"])
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)

    fields = _load_ontology()
    vectors = _load_vectors()
    lots = _iter_lots()

    id_to_vec = {lot["_id"]: vectors.get(_lot_id_for(lot["_file"])) for lot in lots}

    # Precompute similar lots
    sim_map: dict[str, list[dict]] = {}
    for lot in lots:
        vec = id_to_vec.get(lot["_id"]) 
        if not vec:
            sim_map[lot["_id"]] = []
            continue
        scores = []
        for other in lots:
            if other is lot:
                continue
            ov = id_to_vec.get(other["_id"]) 
            if not ov:
                continue
            scores.append((
                _cos_sim(vec, ov),
                other,
            ))
        scores.sort(key=lambda x: x[0], reverse=True)
        items = []
        for score, other in scores[:6]:
            title = other.get("title_en") or next(
                (other.get(f"title_{l}") for l in langs if other.get(f"title_{l}")),
                other.get("_id"),
            )
            thumb = other.get("files", [""])[0]
            items.append({
                "link": f"{other['_id']}.html",
                "title": title,
                "thumb": thumb,
            })
        sim_map[lot["_id"]] = items

    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    recent = []
    for lot in lots:
        ts = lot.get("timestamp")
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            continue
        if dt >= recent_cutoff:
            title = lot.get("title_en") or next(
                (lot.get(f"title_{l}") for l in langs if lot.get(f"title_{l}")),
                lot.get("_id"),
            )
            recent.append({"link": f"{lot['_id']}.html", "title": title, "dt": dt})

    for lot in lots:
        build_page(env, lot, sim_map.get(lot["_id"], []), fields, langs)

    recent.sort(key=lambda x: x["dt"], reverse=True)
    index_tpl = env.get_template("index.html")
    (VIEWS_DIR / "index.html").write_text(index_tpl.render(lots=recent, langs=langs, title="Index"))
    log.info("Site build complete")


if __name__ == "__main__":
    main()
