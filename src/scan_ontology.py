"""Scan lot JSONs and record unique keys with value counts.

The script also collects lots missing translated titles or descriptions
and writes helper text files with all unique values for manual review.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")

# All generated files live in ``data/ontology`` so the folder can be
# inspected or removed without touching the raw lots.
OUTPUT_DIR = Path("data/ontology")
FIELDS_FILE = OUTPUT_DIR / "fields.json"
MISSING_FILE = OUTPUT_DIR / "missing.json"

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
REVIEW_FILES = {f: OUTPUT_DIR / f"{f}.txt" for f in REVIEW_FIELDS}

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


def collect_ontology() -> tuple[dict[str, dict[str, int]], list[dict], dict[str, set[str]]]:
    """Return counts per field, lots missing translations and values."""
    ontology: defaultdict[str, Counter[str]] = defaultdict(Counter)
    missing: list[dict] = []
    values: dict[str, set[str]] = {f: set() for f in REVIEW_FIELDS}
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
            if any(not lot.get(f) for f in REVIEW_FIELDS):
                missing.append(lot)
            for f in REVIEW_FIELDS:
                val = lot.get(f)
                if isinstance(val, str):
                    values[f].add(val)
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
    return result, missing, values


def main() -> None:
    log.info("Scanning ontology", path=str(LOTS_DIR))
    data, missing, values = collect_ontology()
    removed = [k for k in list(data) if k in SKIP_FIELDS or k.startswith(SKIP_PREFIXES)]
    for field in removed:
        data.pop(field, None)
    if removed:
        log.debug("Dropped fields", fields=removed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIELDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log.info("Wrote field counts", path=str(FIELDS_FILE))

    MISSING_FILE.write_text(json.dumps(missing, ensure_ascii=False, indent=2))
    log.info("Wrote lots missing translations", path=str(MISSING_FILE))

    for field, path in REVIEW_FILES.items():
        path.write_text("\n".join(sorted(values[field])))
        log.debug("Wrote values", field=field, path=str(path))


if __name__ == "__main__":
    main()
