"""Generate embeddings for lots and store them as JSON files."""

import json
from pathlib import Path

import argparse
import openai


from config_utils import load_config

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
from log_utils import get_logger, install_excepthook
from token_utils import estimate_tokens

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

# ``chop.py`` mirrors the directory layout of the source messages so lot files
# can be nested several levels deep. ``rglob`` is used to scan everything under
# the root ``data/lots`` directory.
LOTS_DIR = Path("data/lots")
VEC_DIR = Path("data/vectors")




def embed_file(path: Path) -> None:
    """Embed ``path`` and write the vector beside it under ``VEC_DIR``."""
    rel = path.relative_to(LOTS_DIR)
    out = (VEC_DIR / rel).with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        log.debug("Vector up to date", file=str(path))
        return

    chat = rel.parts[0] if len(rel.parts) > 1 else ""
    lot_id = f"{chat}/{path.stem}" if chat else path.stem
    text = path.read_text()
    log.debug("Embedding", id=lot_id, tokens=estimate_tokens(text))
    try:
        resp = openai.embeddings.create(
            model="text-embedding-3-large", input=text
        )
        vec = resp.data[0].embedding
    except Exception:
        log.exception("Embed failed", id=lot_id)
        return

    out.write_text(json.dumps({"id": lot_id, "vec": vec}))
    log.debug("Vector written", path=str(out))


def main(argv: list[str] | None = None) -> None:
    """Embed the file given on the command line."""
    parser = argparse.ArgumentParser(description="Embed a lot JSON file")
    parser.add_argument("file", help="Path to the lot JSON")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        parser.error(f"File not found: {path}")

    log.info("Embedding", file=str(path))
    embed_file(path)
    log.info("Done")


if __name__ == "__main__":
    main()
