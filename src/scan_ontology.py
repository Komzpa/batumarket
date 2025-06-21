"""Scan lot JSONs and record unique keys with value counts.

The script also collects lots missing translated titles or descriptions
and writes helper text files with all unique values for manual review.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from log_utils import get_logger, install_excepthook
from message_utils import gather_chop_input, parse_md

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


def _is_misparsed(lot: dict) -> bool:
    """Return ``True`` when the lot clearly comes from the example prompt."""
    return lot.get("contact:telegram") == "@username"


def collect_ontology() -> tuple[
    dict[str, dict[str, int]],
    dict[str, Counter[str]],
    list[dict],
    list[dict],
]:
    """Return counts per field, value counters, misparsed lots and broken metadata."""
    ontology: defaultdict[str, Counter[str]] = defaultdict(Counter)
    values: dict[str, Counter[str]] = {f: Counter() for f in REVIEW_FIELDS}
    misparsed: list[dict] = []
    broken: list[dict] = []
    for path in LOTS_DIR.rglob("*.json"):
        try:
            lots = json.loads(path.read_text())
        except Exception:
            log.exception("Failed to parse", file=str(path))
            continue
        if isinstance(lots, dict):
            lots = [lots]
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            for k in list(lot):
                if lot[k] == "" or lot[k] is None:
                    del lot[k]
            src = lot.get("source:path")
            if any(not lot.get(f) for f in REVIEW_FIELDS) or _is_misparsed(lot):
                prompt = ""
                if src:
                    try:
                        prompt = gather_chop_input(RAW_DIR / src, MEDIA_DIR)
                    except Exception:
                        log.exception("Failed to build parser input", source=src)
                misparsed.append({"lot": lot, "input": prompt})
            if src:
                meta, _ = parse_md(RAW_DIR / src)
                if not meta.get("id") or not meta.get("chat") or not meta.get("date"):
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
    return result, values, misparsed, broken


def main() -> None:
    log.info("Scanning ontology", path=str(LOTS_DIR))
    data, values, misparsed, broken = collect_ontology()
    removed = [k for k in list(data) if k in SKIP_FIELDS or k.startswith(SKIP_PREFIXES)]
    for field in removed:
        data.pop(field, None)
    if removed:
        log.debug("Dropped fields", fields=removed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIELDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log.info("Wrote field counts", path=str(FIELDS_FILE))

    MISPARSED_FILE.write_text(json.dumps(misparsed, ensure_ascii=False, indent=2))
    log.info("Wrote mis-parsed lots", path=str(MISPARSED_FILE))

    BROKEN_META_FILE.write_text(json.dumps(broken, ensure_ascii=False, indent=2))
    if broken:
        log.info("Wrote broken metadata list", path=str(BROKEN_META_FILE), count=len(broken))

    for field, path in REVIEW_FILES.items():
        counter = dict(sorted(values[field].items(), key=lambda x: (-x[1], x[0])))
        path.write_text(json.dumps(counter, ensure_ascii=False, indent=2))
        log.debug("Wrote values", field=field, path=str(path))


if __name__ == "__main__":
    main()
