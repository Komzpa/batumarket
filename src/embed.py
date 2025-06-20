"""Generate embeddings for lots and store them in Postgres and JSONL."""

import json
from pathlib import Path

import openai
import psycopg2

# ``psycopg2`` is packaged for most distributions so the project sticks to the
# older driver even though the code only relies on basic features.

from config_utils import load_config

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
DB_DSN = cfg.DB_DSN
from log_utils import get_logger, install_excepthook
from token_utils import estimate_tokens

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

# ``chop.py`` mirrors the directory layout of the source messages so lot files
# can be nested several levels deep. ``rglob`` is used to scan everything under
# the root ``data/lots`` directory.
LOTS_DIR = Path("data/lots")
VEC_FILE = Path("data/vectors.jsonl")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS lot_vec(
  lot_id text PRIMARY KEY,
  vec vector(3072)
);
"""


def embed_text(lot_id: str, text: str, cur) -> None:
    cur.execute("SELECT 1 FROM lot_vec WHERE lot_id = %s", [lot_id])
    if cur.fetchone():
        log.debug("Vector already stored", id=lot_id)
        return

    log.debug("Embedding", id=lot_id, tokens=estimate_tokens(text))
    try:
        resp = openai.embeddings.create(
            model="text-embedding-3-large", input=text
        )
        vec = resp.data[0].embedding
    except Exception:
        log.exception("Embed failed", id=lot_id)
        return
    cur.execute(
        "INSERT INTO lot_vec (lot_id, vec) VALUES (%s, %s) ON CONFLICT (lot_id) DO NOTHING",
        [lot_id, vec],
    )
    with VEC_FILE.open("a") as f:
        f.write(json.dumps({"id": lot_id, "vec": vec}) + "\n")


def main() -> None:
    log.info("Embedding lots")
    log.debug("Connecting to Postgres")
    lot_paths = list(LOTS_DIR.rglob("*.json"))
    log.info("Found lot files", count=len(lot_paths))
    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            for path in lot_paths:
                lot_id = path.stem
                text = path.read_text()
                embed_text(lot_id, text, cur)
            conn.commit()
    log.info("Embedding complete")


if __name__ == "__main__":
    main()
