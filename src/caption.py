"""Generate captions for media files using GPT-4o Vision."""

import base64
import hashlib
from pathlib import Path

import openai

from config_utils import load_config

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
from log_utils import get_logger, install_excepthook
from notes_utils import write_md

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

PROMPT = (
    "You see one product.\n"
    "Describe fully: object type, style, color, brand, notable defects, rough size.\n"
    "Output 80-150 words, English."
)

MEDIA_DIR = Path("data/media")
DESC_DIR = Path("data/media_desc")


def caption_file(path: Path) -> str:
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    out = DESC_DIR / f"{sha}.md"
    if out.exists():
        return sha

    image_b64 = base64.b64encode(data).decode()
    message = [
        {"role": "system", "content": PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                }
            ],
        },
    ]
    log.debug("Captioning", sha=sha)
    try:
        resp = openai.chat.completions.create(model="gpt-4o", messages=message)
        text = resp.choices[0].message.content.strip()
    except Exception:
        log.exception("Caption failed", sha=sha)
        return sha

    write_md(out, text)
    return sha


def main() -> None:
    log.info("Captioning media")
    DESC_DIR.mkdir(parents=True, exist_ok=True)
    for path in MEDIA_DIR.glob("*"):
        if path.is_file():
            caption_file(path)
    log.info("Captioning done")


if __name__ == "__main__":
    main()
