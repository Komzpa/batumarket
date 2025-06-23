"""Generate captions for a single image using GPT-4o Vision."""

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Tuple

import openai

from config_utils import load_config
from serde_utils import load_json, write_json

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
LANGS = getattr(cfg, "LANGS", ["en"])
from log_utils import get_logger, install_excepthook
from caption_io import caption_json_path, has_caption
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


def _identify_size(path: Path) -> Tuple[int, int]:
    """Return ``(width, height)`` for ``path`` using ImageMagick."""
    result = subprocess.run(
        ["identify", "-format", "%w %h", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = result.stdout.strip().split()
    return int(w), int(h)


def _prepare_image(path: Path) -> bytes:
    """Resize ``path`` and return the processed JPEG bytes."""
    try:
        width, height = _identify_size(path)
        short = min(width, height)
        scale = 512 / short
        new_w = int(round(width * scale))
        new_h = int(round(height * scale))
        cmd = [
            "convert",
            str(path),
            "-resize",
            f"{new_w}x{new_h}!",
            "-liquid-rescale",
            "512x512!",
            "jpeg:-",
        ]
        log.debug("Resize", width=width, height=height, scaled=f"{new_w}x{new_h}")
        result = subprocess.run(cmd, capture_output=True, check=True)
        log.debug("Seam carved", bytes=len(result.stdout))
        return result.stdout
    except Exception:
        log.exception("Image preprocessing failed", file=str(path))
        return path.read_bytes()


def _guess_chat(path: Path) -> str:
    """Return chat name for ``path`` relative to ``MEDIA_DIR``."""
    try:
        return path.relative_to(MEDIA_DIR).parts[0]
    except Exception:
        return ""


def caption_file(path: Path) -> str:
    """Caption ``path`` with GPT-4o and save ``.caption.json`` beside it."""
    orig = path.read_bytes()
    sha = hashlib.sha256(orig).hexdigest()
    if has_caption(path):
        # Log at info level so users know the file was intentionally skipped.
        log.info("Caption exists", file=str(path))
        return sha

    chat = _guess_chat(path)
    processed = _prepare_image(path)
    image_b64 = base64.b64encode(processed).decode()
    prompt = CAPTION_PROMPT.format(chat=chat, langs=", ".join(LANGS))
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
    log.debug("Captioning", sha=sha, chat=chat, file=str(path))
    log.debug("OpenAI request", messages=message)
    schema = {
        "type": "object",
        "properties": {f"caption_{l}": {"type": "string"} for l in LANGS},
        "required": [f"caption_{l}" for l in LANGS],
        "additionalProperties": False,
    }
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=message,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"schema": schema, "name": "describe_image", "strict": True},
            },
        )
        msg = resp.choices[0].message
        raw = getattr(msg, "content", None)
        if raw is None and getattr(msg, "tool_calls", None):
            raw = msg.tool_calls[0].function.arguments
        log.info("OpenAI response", text=raw, file=str(path))
        data = json.loads(raw)
    except Exception:
        log.exception("Caption failed", sha=sha, file=str(path))
        return sha

    missing = [l for l in LANGS if f"caption_{l}" not in data]
    if missing:
        log.error("Missing caption languages", file=str(path), missing=missing)
        return sha

    out_path = caption_json_path(path)
    existing = load_json(out_path) if out_path.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update({k: data[k] for k in data if k.startswith("caption_")})
    write_json(out_path, existing)
    log.info("Caption", file=str(path), text=existing)
    return sha


def main() -> None:
    parser = argparse.ArgumentParser(description="Caption an image")
    parser.add_argument("image", help="Path to the image file")
    args = parser.parse_args()

    path = Path(args.image)
    if not path.exists():
        parser.error(f"File not found: {path}")

    log.info("Captioning single file", file=str(path))
    caption_file(path)
    log.info("Done")


if __name__ == "__main__":
    main()
