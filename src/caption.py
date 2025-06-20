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
from token_utils import estimate_tokens

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

# Detailed prompt stored separately so it is easy to tweak without touching the
# code.  ``{chat}`` placeholder gives the model some context about the source
# chat.  Keep an eye on the token count since vision prompts can get pricey.
CAPTION_PROMPT = Path("prompts/captioner_prompt.md").read_text(encoding="utf-8")
log.debug("Prompt tokens", count=estimate_tokens(CAPTION_PROMPT))

MEDIA_DIR = Path("data/media")


def _guess_chat(path: Path) -> str:
    """Return chat name for ``path`` relative to ``MEDIA_DIR``."""
    try:
        return path.relative_to(MEDIA_DIR).parts[0]
    except Exception:
        return ""


def caption_file(path: Path) -> str:
    """Caption ``path`` with GPT-4o and save ``.caption.md`` beside it."""
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    out = path.with_suffix(".caption.md")
    if out.exists():
        return sha

    chat = _guess_chat(path)
    image_b64 = base64.b64encode(data).decode()
    prompt = CAPTION_PROMPT.format(chat=chat)
    message = [
        {"role": "system", "content": prompt},
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
    log.debug("Captioning", sha=sha, chat=chat)
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
    for path in MEDIA_DIR.rglob("*"):
        if path.is_file() and not path.name.endswith(".md"):
            caption_file(path)
    log.info("Captioning done")


if __name__ == "__main__":
    main()
