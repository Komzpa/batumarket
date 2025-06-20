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
import shutil
from datetime import datetime, timedelta, timezone

from jinja2 import Environment, FileSystemLoader

try:
    from sklearn.neighbors import NearestNeighbors
    _has_sklearn = True
except Exception:
    _has_sklearn = False

from config_utils import load_config
from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
VIEWS_DIR = Path("data/views")
TEMPLATES = Path("templates")
VEC_DIR = Path("data/vectors")
ONTOLOGY = Path("data/ontology.json")
RAW_DIR = Path("data/raw")


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
    fields = sorted(data.keys())
    log.info("Loaded ontology", count=len(fields))
    return fields


def _parse_md(path: Path) -> tuple[dict, str]:
    """Return metadata dict and message text from ``path``."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    meta: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = "\n".join(lines[body_start:])
    return meta, body


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
    """Render ``lot`` into separate HTML files for every language."""
    for lang in langs:
        images = []
        for rel in lot.get("files", []):
            p = Path("data/media") / rel
            cap = p.with_suffix(".caption.md")
            caption = cap.read_text(encoding="utf-8") if cap.exists() else ""
            images.append({"path": rel, "caption": caption})

        # Drop internal helper fields that are meaningless to end users.
        attrs = {
            k: v
            for k, v in lot.items()
            if k not in {"files"}
            and not k.startswith("title_")
            and not k.startswith("description_")
            and not k.startswith("source:")
            and not k.startswith("_")
        }
        sorted_attrs = {k: attrs[k] for k in fields if k in attrs}
        for k in attrs:
            if k not in sorted_attrs:
                sorted_attrs[k] = attrs[k]

        # Show the original message text for context if available.
        orig_text = ""
        src = lot.get("source:path")
        if src:
            _, orig_text = _parse_md(RAW_DIR / src)

        chat = lot.get("source:chat")
        mid = lot.get("source:message_id")
        tg_link = f"https://t.me/{chat}/{mid}" if chat and mid else ""

        template = env.get_template("lot.html")
        out = VIEWS_DIR / f"{lot['_id']}_{lang}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        page_similar = [
            {
                "link": f"{item['id']}_{lang}.html",
                "title": item["title"],
                "thumb": item["thumb"],
            }
            for item in similar
        ]
        out.write_text(
            template.render(
                title=lot.get(f"title_{lang}", "Lot"),
                lot=lot,
                images=images,
                attrs=sorted_attrs,
                orig_text=orig_text,
                description=lot.get(f"description_{lang}", ""),
                tg_link=tg_link,
                similar=page_similar,
                langs=langs,
                current_lang=lang,
                page_basename=lot["_id"],
                home_link=f"index_{lang}.html",
            )
        )
        log.debug("Wrote", path=str(out))


def main() -> None:
    log.info("Building site")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    cfg = load_config()
    langs = getattr(cfg, "LANGS", ["en"])
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy CSS and JS so the generated pages are standalone
    static_src = TEMPLATES / "static"
    static_dst = VIEWS_DIR / "static"
    if static_src.exists():
        if static_dst.exists():
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst)
        log.debug("Copied static assets", src=str(static_src), dst=str(static_dst))

    log.debug("Loading ontology")
    fields = _load_ontology()
    log.debug("Loading vectors")
    vectors = _load_vectors()
    log.debug("Loading lots")
    lots = _iter_lots()

    id_to_vec = {lot["_id"]: vectors.get(_lot_id_for(lot["_file"])) for lot in lots}

    log.info("Computing similar lots", count=len(lots))
    sim_map: dict[str, list[dict]] = {}

    vec_ids = [lot["_id"] for lot in lots if id_to_vec.get(lot["_id"])]
    if _has_sklearn and vec_ids:
        matrix = [id_to_vec[i] for i in vec_ids]
        nn = NearestNeighbors(n_neighbors=7, metric="cosine")
        nn.fit(matrix)
        dists, idxs = nn.kneighbors(matrix)
        idx_to_id = {i: vec_ids[i] for i in range(len(vec_ids))}
        lookup = {lot["_id"]: lot for lot in lots}
        for i, lot_id in enumerate(vec_ids):
            items = []
            for dist, other_idx in zip(dists[i][1:], idxs[i][1:]):
                other = lookup[idx_to_id[other_idx]]
                title = other.get("title_en") or next(
                    (other.get(f"title_{l}") for l in langs if other.get(f"title_{l}")),
                    other.get("_id"),
                )
                files = other.get("files") or []
                thumb = files[0] if files else ""
                items.append({"id": other["_id"], "title": title, "thumb": thumb})
            sim_map[lot_id] = items
    else:
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
                scores.append((_cos_sim(vec, ov), other))
            scores.sort(key=lambda x: x[0], reverse=True)
            items = []
            for score, other in scores[:6]:
                title = other.get("title_en") or next(
                    (other.get(f"title_{l}") for l in langs if other.get(f"title_{l}")),
                    other.get("_id"),
                )
                files = other.get("files") or []
                thumb = files[0] if files else ""
                items.append({"id": other["_id"], "title": title, "thumb": thumb})
            sim_map[lot["_id"]] = items

    # ``datetime.utcnow`` returns a naive object which breaks comparisons with
    # timezone-aware timestamps coming from lots.  Normalize everything to UTC.
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = []
    for lot in lots:
        ts = lot.get("timestamp")
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                # Older data might have naive timestamps. Assume UTC for
                # backwards compatibility so comparisons work.
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt >= recent_cutoff:
            titles = {lang: lot.get(f"title_{lang}") for lang in langs}
            seller = (
                lot.get("contact:phone")
                or lot.get("contact:telegram")
                or lot.get("contact:instagram")
                or lot.get("contact:viber")
                or lot.get("contact:whatsapp")
                or lot.get("seller")
            )
            recent.append(
                {
                    "id": lot["_id"],
                    "titles": titles,
                    "dt": dt,
                    "price": lot.get("price"),
                    "seller": seller,
                }
            )

    for lot in lots:
        log.debug("Rendering", id=lot["_id"])
        build_page(env, lot, sim_map.get(lot["_id"], []), fields, langs)

    recent.sort(key=lambda x: x["dt"], reverse=True)

    log.debug("Writing index pages")
    index_tpl = env.get_template("index.html")
    for lang in langs:
        items_lang = []
        for item in recent:
            title = item["titles"].get(lang) or next(
                (item["titles"].get(l) for l in langs if item["titles"].get(l)),
                item["id"],
            )
            items_lang.append(
                {
                    "link": f"{item['id']}_{lang}.html",
                    "title": title,
                    "dt": item["dt"],
                    "price": item.get("price"),
                    "seller": item.get("seller"),
                }
            )
        out = VIEWS_DIR / f"index_{lang}.html"
        out.write_text(
            index_tpl.render(
                items=items_lang,
                langs=langs,
                current_lang=lang,
                page_basename="index",
                title="Index",
                home_link=f"index_{lang}.html",
            )
        )
        log.debug("Wrote", path=str(out))
    if langs:
        default = VIEWS_DIR / "index.html"
        src = VIEWS_DIR / f"index_{langs[0]}.html"
        default.write_text(src.read_text())
        log.debug("Wrote", path=str(default))
    log.info("Site build complete")


if __name__ == "__main__":
    main()
