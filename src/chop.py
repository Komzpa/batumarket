"""Split telegram messages into lots with GPT-4o."""

import json
from pathlib import Path

import openai

from config import OPENAI_KEY
from log_utils import get_logger, install_excepthook
from notes_utils import read_md
from token_utils import estimate_tokens

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

RAW_DIR = Path("data/raw")
MEDIA_DESC = Path("data/media_desc")
LOTS_DIR = Path("data/lots")

SYSTEM_PROMPT = (
    "You will receive a raw marketplace post with optional image captions.\n"
    "Return a JSON list of separate lots with their titles, description_en and media SHA references."
)


def process_message(msg_path: Path) -> None:
    text = read_md(msg_path)
    captions = []
    for sha_path in MEDIA_DESC.glob("*.md"):
        captions.append(read_md(sha_path))
    prompt = text + "\n" + "\n".join(captions)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    log.debug("Prompt tokens", count=estimate_tokens(prompt))
    try:
        resp = openai.chat.completions.create(model="gpt-4o", messages=messages)
        lots = json.loads(resp.choices[0].message.content)
    except Exception:
        log.exception("Failed to chop", file=str(msg_path))
        return
    out = LOTS_DIR / msg_path.name.replace(".md", ".json")
    out.write_text(json.dumps(lots, ensure_ascii=False, indent=2))
    log.debug("Wrote", path=str(out))


def main() -> None:
    LOTS_DIR.mkdir(parents=True, exist_ok=True)
    for p in RAW_DIR.glob("*/*.md"):
        process_message(p)


if __name__ == "__main__":
    main()
