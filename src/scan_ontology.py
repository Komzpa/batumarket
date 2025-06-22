"""Scan lot JSONs and record unique keys with value counts.

The script also collects lots missing translated titles or descriptions
and writes helper text files with all unique values for manual review.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from log_utils import get_logger, install_excepthook
from lot_io import get_seller, get_timestamp
from message_utils import gather_chop_input
from post_io import (
    read_post,
    get_contact as get_post_contact,
    get_timestamp as get_post_timestamp,
    is_broken_meta,
)
from serde_utils import write_json
from lot_io import read_lots

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")

# All generated files live in ``data/ontology`` so the folder can be
# inspected or removed without touching the raw lots.
OUTPUT_DIR = Path("data/ontology")
FIELDS_FILE = OUTPUT_DIR / "fields.json"
MISPARSED_FILE = OUTPUT_DIR / "misparsed.json"
BROKEN_META_FILE = OUTPUT_DIR / "broken_meta.json"
FRAUD_FILE = OUTPUT_DIR / "fraud.json"

REVIEW_FIELDS = [
    "title_en",
    "description_en",
    "title_ru",
    "description_ru",
    "title_ka",
    "description_ka",
]

# Mapping from field name to file path where unique values are stored for
# manual review.
REVIEW_FILES = {f: OUTPUT_DIR / f"{f}.json" for f in REVIEW_FIELDS}

# Fields that carry volatile per-message metadata or language specific
# duplicates.  Dropping them keeps ``ontology.json`` focused on the
# reusable attributes of each lot.
SKIP_FIELDS = {
    "timestamp",
    "contact:telegram",
    "source:path",
    "source:message_id",
    "source:chat",
    "files",
}

# Any key that starts with these prefixes is removed from the final counts.
SKIP_PREFIXES = ("title_", "description_")



def _is_misparsed(lot: dict, meta: dict | None = None) -> bool:
    """Return ``True`` for obviously invalid lots or source posts."""
    if lot.get("contact:telegram") == "@username":
        log.debug("Example contact", id=lot.get("_id"))
        return True
    if get_timestamp(lot) is None:
        log.debug("Missing timestamp", id=lot.get("_id"))
        return True
    if get_seller(lot) is None:
        log.debug("Missing seller info", id=lot.get("_id"))
        return True
    if meta is not None:
        if is_broken_meta(meta):
            if get_post_timestamp(meta) is None:
                log.debug("Missing raw timestamp", id=lot.get("_id"))
            if get_post_contact(meta) is None:
                log.debug("Missing raw contact", id=lot.get("_id"))
            return True
    if any(not lot.get(f) for f in REVIEW_FIELDS):
        log.debug("Missing translations", id=lot.get("_id"))
        return True
    return False


def collect_ontology() -> tuple[
    dict[str, dict[str, int]],
    dict[str, Counter[str]],
    list[dict],
    list[dict],
    list[dict],
]:
    """Return counts per field, value counters, misparsed lots and broken metadata."""
    ontology: defaultdict[str, Counter[str]] = defaultdict(Counter)
    values: dict[str, Counter[str]] = {f: Counter() for f in REVIEW_FIELDS}
    misparsed: list[dict] = []
    broken: list[dict] = []
    fraud: list[dict] = []
    has_raw = RAW_DIR.exists()
    if not has_raw:
        log.debug("RAW_DIR missing", path=str(RAW_DIR))
    for path in LOTS_DIR.rglob("*.json"):
        lots = read_lots(path)
        if not lots:
            continue
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            src = lot.get("source:path")
            meta = None
            if src and has_raw:
                meta, _ = read_post(RAW_DIR / src)
            if _is_misparsed(lot, meta):
                prompt = ""
                if src and has_raw:
                    try:
                        prompt = gather_chop_input(RAW_DIR / src, MEDIA_DIR)
                    except Exception:
                        log.exception("Failed to build parser input", source=src)
                misparsed.append({"lot": lot, "input": prompt})
            if lot.get("fraud") is not None:
                prompt = ""
                if src and has_raw:
                    try:
                        prompt = gather_chop_input(RAW_DIR / src, MEDIA_DIR)
                    except Exception:
                        log.exception("Failed to build parser input", source=src)
                fraud.append({"lot": lot, "input": prompt})
            if src and has_raw:
                if meta is None:
                    meta, _ = read_post(RAW_DIR / src)
                if is_broken_meta(meta):
                    chat = lot.get("source:chat") or meta.get("chat")
                    mid = lot.get("source:message_id") or meta.get("id")
                    if chat and mid:
                        broken.append({"chat": chat, "id": int(mid)})
            for f in REVIEW_FIELDS:
                val = lot.get(f)
                if isinstance(val, str):
                    values[f][val] += 1
            for key, value in lot.items():
                if isinstance(value, (dict, list)):
                    val = json.dumps(value, ensure_ascii=False, sort_keys=True)
                else:
                    val = str(value)
                ontology[key][val] += 1
    # Convert counters to plain dicts sorted by count
    result: dict[str, dict[str, int]] = {}
    for key, counter in ontology.items():
        result[key] = dict(sorted(counter.items(), key=lambda x: (-x[1], x[0])))
    return result, values, misparsed, broken, fraud


def main() -> None:
    log.info("Scanning ontology", path=str(LOTS_DIR))
    if not LOTS_DIR.exists() or not any(LOTS_DIR.rglob("*.json")):
        log.warning("Lots directory missing or empty", path=str(LOTS_DIR))
        return
    data, values, misparsed, broken, fraud = collect_ontology()
    removed = [k for k in list(data) if k in SKIP_FIELDS or k.startswith(SKIP_PREFIXES)]
    for field in removed:
        data.pop(field, None)
    if removed:
        log.debug("Dropped fields", fields=removed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(FIELDS_FILE, data)
    log.info("Wrote field counts", path=str(FIELDS_FILE))

    write_json(MISPARSED_FILE, misparsed)
    log.info("Wrote mis-parsed lots", path=str(MISPARSED_FILE))

    write_json(FRAUD_FILE, fraud)
    if fraud:
        log.info(
            "Wrote fraud list",
            path=str(FRAUD_FILE),
            count=len(fraud),
        )

    write_json(BROKEN_META_FILE, broken)
    if broken:
        log.info(
            "Wrote broken metadata list",
            path=str(BROKEN_META_FILE),
            count=len(broken),
        )

    for field, path in REVIEW_FILES.items():
        counter = dict(sorted(values[field].items(), key=lambda x: (-x[1], x[0])))
        write_json(path, counter)
        log.debug("Wrote values", field=field, path=str(path))


if __name__ == "__main__":
    main()
