"""Split Telegram messages into lots using GPT-4o.

The system prompt is built from ``prompts/chopper_prompt.md`` which details the
expected JSON schema and message taxonomy.  Any change to that file immediately
affects the extraction logic.
"""

import json
import ast
from pathlib import Path

import openai

from config_utils import load_config

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
LANGS = cfg.LANGS
from log_utils import get_logger, install_excepthook
from notes_utils import read_md

# Blueprint describing expected fields and message taxonomy used by the model.
BLUEPRINT = Path("prompts/chopper_prompt.md").read_text(encoding="utf-8")
from token_utils import estimate_tokens

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

RAW_DIR = Path("data/raw")
MEDIA_DIR = Path("data/media")
LOTS_DIR = Path("data/lots")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _build_prompt(text: str, files: list[str], captions: list[str]) -> str:
    """Return prompt combining message text with captioned file names."""
    parts = []
    if text.strip():
        parts.append(f"Message text:\n{text.strip()}")
    for file, caption in zip(files, captions):
        parts.append(f"Image {file}:\n{caption.strip()}")
    return "\n\n".join(parts)


def _parse_md(path: Path) -> tuple[dict, str]:
    """Return metadata dict and message text."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    meta = {}
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body = "\n".join(lines[body_start:])
    return meta, body

# System prompt appended to the blueprint.  Explicitly instruct the model to
# respond with *only* JSON, no code fences or extra text.  The API request will
# also enforce this via ``response_format``.
SYSTEM_PROMPT = (
    BLUEPRINT
    + "\n\nYou will receive a raw marketplace post with optional image captions.\n"
    "Return a JSON array of separate lots with file references.\n"
    "For each of these languages: {langs}, produce title_<lang> and description_<lang> fields.\n"
    "Respond with JSON only. Do not use code fences or any extra text."
)


def process_message(msg_path: Path) -> None:
    rel = msg_path.relative_to(RAW_DIR)
    out = LOTS_DIR / rel.with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        log.debug("Skipping existing lot file", path=str(out))
        return

    log.info("Processing message", path=str(msg_path))

    meta, text = _parse_md(msg_path)
    files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
    captions = []
    for rel in files:
        p = MEDIA_DIR / rel
        if not p.exists():
            log.info("Skipping message", path=str(msg_path), reason="missing-media", file=str(p))
            return
        if p.suffix.lower() in IMAGE_EXTS:
            cap = p.with_suffix(".caption.md")
            if not cap.exists():
                log.info("Skipping message", path=str(msg_path), reason="missing-caption", file=str(p))
                return
            caption_text = read_md(cap)
            log.debug("Found caption", file=str(p), text=caption_text)
            captions.append(caption_text)
    # Combine the original message text with image captions. This ensures GPT
    # has full context rather than captions alone.
    prompt = _build_prompt(text, files, captions)
    system_prompt = SYSTEM_PROMPT.replace("{langs}", ", ".join(LANGS))
    log.debug("Blueprint tokens", count=estimate_tokens(BLUEPRINT))
    log.debug("System prompt tokens", count=estimate_tokens(system_prompt))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    log.debug("Prompt tokens", count=estimate_tokens(prompt), langs=LANGS)
    log.info("OpenAI request", messages=messages)
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        log.info("OpenAI response", text=raw)
        text_json = raw.strip()
        if text_json.startswith("```"):
            text_json = text_json.strip("`\n")
        lots = json.loads(text_json)
    except Exception:
        log.exception("Failed to chop", file=str(msg_path))
        return
    if isinstance(lots, dict):
        lots = [lots]
    source_path = str(msg_path.relative_to(RAW_DIR))
    for lot in lots:
        lot.setdefault("source:chat", meta.get("chat"))
        lot.setdefault("source:message_id", str(meta.get("id")))
        lot.setdefault("source:path", source_path)
        if files:
            lot.setdefault("files", files)
        for lang in LANGS:
            lot.setdefault(f"title_{lang}", "")
            lot.setdefault(f"description_{lang}", "")
    out.write_text(json.dumps(lots, ensure_ascii=False, indent=2))
    log.debug("Wrote", path=str(out))


def main() -> None:
    log.info("Chopping lots")
    LOTS_DIR.mkdir(parents=True, exist_ok=True)
    # Sort newest first so freshly scraped messages are chopped right away.
    files = sorted(
        RAW_DIR.glob("*/*/*/*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    log.info("Found messages", count=len(files), order="mtime-desc")
    if not files:
        log.warning("No raw messages", path=str(RAW_DIR))
    for p in files:
        process_message(p)
    log.info("Chopping complete", processed=len(files))


if __name__ == "__main__":
    main()
