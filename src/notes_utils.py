"""Small helper functions to read and write markdown files."""

from pathlib import Path


def read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def read_md(path: str) -> str:
    return read_text(path)


def write_md(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip() + "\n", encoding="utf-8")


def collect_notes() -> str:
    """Return combined notes if ``notes/`` exists."""
    notes_dir = Path("notes")
    if not notes_dir.exists():
        return ""
    parts = []
    for f in sorted(notes_dir.glob("*.md")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)
