"""Translate lot texts into configured languages using GPT-4o."""

import json
from pathlib import Path

import openai

from config import OPENAI_KEY, LANGS
from log_utils import get_logger, install_excepthook
from notes_utils import write_md

log = get_logger().bind(script=__file__)
install_excepthook(log)

openai.api_key = OPENAI_KEY

LOTS_DIR = Path("data/lots")

SYSTEM_PROMPT = "Translate the following text into {lang}. Return Markdown."


def translate_file(path: Path) -> None:
    data = json.loads(path.read_text())
    text = data.get("description_en", "")
    for lang in LANGS:
        if lang == "en":
            continue
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(lang=lang)},
            {"role": "user", "content": text},
        ]
        try:
            resp = openai.chat.completions.create(model="gpt-4o", messages=messages)
            translated = resp.choices[0].message.content.strip()
            data[f"description_{lang}"] = translated
        except Exception:
            log.exception("Translate failed", file=str(path), lang=lang)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    for p in LOTS_DIR.glob("*.json"):
        translate_file(p)


if __name__ == "__main__":
    main()
