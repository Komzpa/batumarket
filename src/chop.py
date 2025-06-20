"""Split Telegram messages into lots using GPT-4o.

The system prompt is built from ``prompts/chopper_prompt.md`` which details the
expected JSON schema and message taxonomy.  Any change to that file immediately
affects the extraction logic.
"""

import json
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

# System prompt appended to the blueprint.  Explicitly instruct the model to
# respond with *only* JSON, no code fences or extra text.  The API request will
# also enforce this via ``response_format``.
SYSTEM_PROMPT = (
    BLUEPRINT
    + "\n\nYou will receive a raw marketplace post with optional image captions.\n"
    "Return a JSON list of separate lots with media SHA references.\n"
    "For each of these languages: {langs}, produce title_<lang> and description_<lang> fields.\n"
    "Respond with JSON only."
)


def process_message(msg_path: Path) -> None:
    out = LOTS_DIR / msg_path.name.replace(".md", ".json")
    if out.exists():
        log.debug("Skipping existing lot file", path=str(out))
        return

    text = read_md(msg_path)
    captions = []
    for cap_path in MEDIA_DIR.rglob("*.caption.md"):
        captions.append(read_md(cap_path))
    prompt = text + "\n" + "\n".join(captions)
    system_prompt = SYSTEM_PROMPT.format(langs=", ".join(LANGS))
    log.debug("Blueprint tokens", count=estimate_tokens(BLUEPRINT))
    log.debug("System prompt tokens", count=estimate_tokens(system_prompt))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    log.debug("Prompt tokens", count=estimate_tokens(prompt), langs=LANGS)
    try:
        # ``response_format`` ensures GPT-4o emits a valid JSON object with no
        # extra text.  ``temperature`` 0 keeps the output deterministic.
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        lots = json.loads(resp.choices[0].message.content)
    except Exception:
        log.exception("Failed to chop", file=str(msg_path))
        return
    out.write_text(json.dumps(lots, ensure_ascii=False, indent=2))
    log.debug("Wrote", path=str(out))


def main() -> None:
    log.info("Chopping lots")
    LOTS_DIR.mkdir(parents=True, exist_ok=True)
    for p in RAW_DIR.glob("*/*.md"):
        process_message(p)
    log.info("Chopping complete")


if __name__ == "__main__":
    main()
