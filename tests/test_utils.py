from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from notes_utils import write_md, read_md
from token_utils import estimate_tokens


def test_write_and_read_md(tmp_path: Path):
    file_path = tmp_path / "note.md"
    write_md(file_path, "hello")
    assert file_path.read_text() == "hello\n"
    assert read_md(file_path) == "hello\n"


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 20) == 5
