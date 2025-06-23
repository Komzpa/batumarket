"""Helpers for translated caption files stored beside images."""

from pathlib import Path

from config_utils import load_config
from serde_utils import read_md, load_json, write_json
from log_utils import get_logger

_LANGS: list[str] | None = None

CAPTION_SUFFIX = ".caption.json"
LEGACY_SUFFIX = ".caption.md"

log = get_logger().bind(module=__name__)


def _get_langs() -> list[str]:
    """Return configured languages, caching the result."""
    global _LANGS
    if _LANGS is None:
        cfg = load_config()
        _LANGS = getattr(cfg, "LANGS", ["en"])
    return _LANGS


def caption_json_path(image: Path) -> Path:
    """Return new-style caption path for ``image``."""
    return image.with_suffix(CAPTION_SUFFIX)


def caption_md_path(image: Path) -> Path:
    """Return legacy Markdown caption path for ``image``."""
    return image.with_suffix(LEGACY_SUFFIX)


def has_caption(image: Path) -> bool:
    """Return ``True`` when any caption exists for ``image``."""
    return caption_json_path(image).exists() or caption_md_path(image).exists()


def read_caption(image: Path, lang: str | None = None) -> str:
    """Return caption for ``image`` in ``lang`` or empty string when missing."""
    langs = _get_langs()
    lang = lang or langs[0]
    json_path = caption_json_path(image)
    if json_path.exists():
        data = load_json(json_path)
        if isinstance(data, dict):
            key = f"caption_{lang}"
            text = data.get(key, "")
            if text and not text.endswith("\n"):
                text += "\n"
            return text
    return read_md(caption_md_path(image))


def write_caption(image: Path, text: str, lang: str | None = None) -> None:
    """Write ``text`` as ``lang`` caption for ``image``."""
    langs = _get_langs()
    lang = lang or langs[0]
    path = caption_json_path(image)
    data = {f"caption_{l}": "" for l in langs}
    if path.exists():
        prev = load_json(path)
        if isinstance(prev, dict):
            data.update(prev)
    data[f"caption_{lang}"] = text
    write_json(path, data)
    log.debug("Wrote caption", path=str(path))

