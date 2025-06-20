"""Scan lot JSONs and record unique keys with value counts."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
OUTPUT_FILE = Path("data/ontology.json")

# Fields that carry volatile per-message metadata or language specific
# duplicates.  Dropping them keeps ``ontology.json`` focused on the
# reusable attributes of each lot.
SKIP_FIELDS = {
    "timestamp",
    "contact:telegram",
    "source:path",
    "source:message_id",
    "source:chat",
    "description_ka",
    "title_ka",
    "description_en",
    "title_en",
    "files",
}


def collect_ontology() -> dict[str, dict[str, int]]:
    """Return dictionary mapping field names to value counts."""
    ontology: defaultdict[str, Counter[str]] = defaultdict(Counter)
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
    return result


def main() -> None:
    log.info("Scanning ontology", path=str(LOTS_DIR))
    data = collect_ontology()
    removed = [f for f in SKIP_FIELDS if f in data]
    for field in removed:
        data.pop(field, None)
    if removed:
        log.debug("Dropped fields", fields=removed)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log.info("Wrote ontology", path=str(OUTPUT_FILE))


if __name__ == "__main__":
    main()
