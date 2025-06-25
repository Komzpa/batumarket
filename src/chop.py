"""Split Telegram messages into lots using GPT-4o.

The system prompt is built from ``prompts/chopper_prompt.md`` which details the
expected JSON schema and message taxonomy.  Any change to that file immediately
affects the extraction logic.
"""

import argparse
import json
import ast
from pathlib import Path

import openai

from config_utils import load_config

cfg = load_config()
OPENAI_KEY = cfg.OPENAI_KEY
LANGS = cfg.LANGS
CHOP_MODELS = getattr(
    cfg,
    "CHOP_MODELS",
    [
        {"model": "gpt-4o-mini"},
        {"model": "gpt-4o"},
    ],
)
from log_utils import get_logger, install_excepthook
from caption_io import read_caption, has_caption
from post_io import read_post, raw_post_path, RAW_DIR
from lot_io import valid_lots, needs_cleanup
from typing import Iterable
from message_utils import build_prompt
import embed

# Blueprint describing expected fields and message taxonomy used by the model.
BLUEPRINT = Path("prompts/chopper_prompt.md").read_text(encoding="utf-8")
from token_utils import estimate_tokens
from moderation import should_skip_message

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY
OPENAI_TIMEOUT = 900  # maximum seconds to wait for GPT-4o
MEDIA_DIR = Path("data/media")
LOTS_DIR = Path("data/lots")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def has_misc_deal(lots: Iterable[dict]) -> bool:
    """Return True when any lot is classified as misc or announcement."""
    for lot in lots:
        deal = lot.get("market:deal")
        if isinstance(deal, list):
            deal = deal[0] if deal else None
        if isinstance(deal, str) and deal in {"misc", "announcement"}:
            return True
    return False

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
    """Extract lots from ``msg_path`` and save them under ``LOTS_DIR``."""
    rel = msg_path.relative_to(RAW_DIR)
    out = LOTS_DIR / rel.with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        log.debug("Skipping existing lot file", path=str(out))
        return

    log.info("Processing message", path=str(msg_path))

    meta, text = read_post(msg_path)
    if should_skip_message(meta, text):
        log.info("Skipping message", path=str(msg_path), reason="moderation")
        return
    files = ast.literal_eval(meta.get("files", "[]")) if "files" in meta else []
    captions = []
    for rel in files:
        p = MEDIA_DIR / rel
        if not p.exists():
            log.info("Skipping message", path=str(msg_path), reason="missing-media", file=str(p))
            return
        if p.suffix.lower() in IMAGE_EXTS:
            if not has_caption(p):
                log.info("Skipping message", path=str(msg_path), reason="missing-caption", file=str(p))
                return
            caption_text = read_caption(p)
            log.debug("Found caption", file=str(p), text=caption_text)
            captions.append(caption_text)

    if not text.strip() and not captions:
        log.info("Skipping message", path=str(msg_path), reason="empty")
        return
    # Combine the original message text with image captions. This ensures GPT
    # has full context rather than captions alone.
    prompt = build_prompt(text, files, captions)
    system_prompt = SYSTEM_PROMPT.replace("{langs}", ", ".join(LANGS))
    log.debug("Blueprint tokens", count=estimate_tokens(BLUEPRINT))
    log.debug("System prompt tokens", count=estimate_tokens(system_prompt))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    log.debug("Prompt tokens", count=estimate_tokens(prompt), langs=LANGS)
    log.info("OpenAI request", messages=messages)
    schema = {
        "type": "object",
        "properties": {
            "lots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title_en": {"type": "string"},
                        "description_en": {"type": "string"},
                        "title_ru": {"type": "string"},
                        "description_ru": {"type": "string"},
                        "title_ka": {"type": "string"},
                        "description_ka": {"type": "string"},
                    },
                    "required": [
                        "title_en",
                        "description_en",
                        "title_ru",
                        "description_ru",
                        "title_ka",
                        "description_ka",
                    ],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["lots"],
        "additionalProperties": False,
    }
    lots = None
    mini_lots = None
    for idx, params in enumerate(CHOP_MODELS):
        try:
            log.info("Calling model", model=params)
            resp = openai.chat.completions.create(
                messages=messages,
                temperature=0,
                timeout=OPENAI_TIMEOUT,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "schema": schema,
                        "name": "extract_lots",
                        "strict": False,
                    },
                },
                **params,
            )
            raw = resp.choices[0].message.content
            log.info("OpenAI response", text=raw)
            lots_data = json.loads(raw)
        except Exception as exc:
            log.exception("Failed to chop", file=str(msg_path), model=params, error=str(exc))
            continue
        if isinstance(lots_data, dict):
            lots = lots_data.get("lots")
            if lots is None:
                lots = [lots_data]
        else:
            lots = lots_data
        if valid_lots(lots):
            log.info("Model succeeded", model=params)
            if idx == 0 and params.get("model") == "gpt-4o-mini" and len(CHOP_MODELS) > 1:
                if len(lots) > 1 or needs_cleanup(lots) or has_misc_deal(lots):
                    log.info(
                        "Mini model result needs full model", count=len(lots)
                    )
                    mini_lots = lots
                    lots = None
                    continue
            break
        log.info("Invalid result", model=params)
        lots = None
    if lots is None:
        if mini_lots is not None:
            log.info("Falling back to mini model result")
            lots = mini_lots
        else:
            log.error("All models failed", file=str(msg_path))
            return
    source_path = str(msg_path.relative_to(RAW_DIR))
    for lot in lots:
        lot.setdefault("source:chat", meta.get("chat"))
        lot.setdefault("source:message_id", str(meta.get("id")))
        lot.setdefault("source:path", source_path)
        lot.setdefault("source:author:telegram", meta.get("sender_username"))
        lot.setdefault("source:author:name", meta.get("sender_name"))
        # Always override the timestamp with the actual message date so the
        # LLM does not hallucinate this field.  ``chop.py`` may receive
        # existing timestamps from the model but they are unreliable.
        if meta.get("date"):
            lot["timestamp"] = meta["date"]
        if files:
            lot.setdefault("files", files)
        for lang in LANGS:
            lot.setdefault(f"title_{lang}", "")
            lot.setdefault(f"description_{lang}", "")
    out.write_text(json.dumps(lots, ensure_ascii=False, indent=2))
    log.debug("Wrote", path=str(out))
    try:
        embed.embed_file(out)
    except Exception:
        log.exception("Embedding failed", path=str(out))


def main(argv: list[str] | None = None) -> None:
    """Process a single message file passed on the command line."""
    parser = argparse.ArgumentParser(description="Chop a Telegram message into lots")
    parser.add_argument("message", help="Path to the message .md file")
    args = parser.parse_args(argv)

    LOTS_DIR.mkdir(parents=True, exist_ok=True)
    msg_path = Path(args.message)
    if not msg_path.exists():
        parser.error(f"Message file not found: {msg_path}")

    log.info("Chopping message", file=str(msg_path))
    process_message(msg_path)


if __name__ == "__main__":
    main()
