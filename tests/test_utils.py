from pathlib import Path
import sys
from datetime import datetime, timezone
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from notes_utils import write_md, read_md
from token_utils import estimate_tokens
from post_io import write_post, read_post
from caption_io import write_caption, read_caption
from lot_io import write_lots, read_lots


def test_write_and_read_md(tmp_path: Path):
    file_path = tmp_path / "note.md"
    write_md(file_path, "hello")
    assert file_path.read_text() == "hello\n"
    assert read_md(file_path) == "hello\n"


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 20) == 5


def test_post_roundtrip(tmp_path: Path):
    path = tmp_path / "post.md"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta = {"id": 1, "chat": "test", "date": now, "sender_name": "user"}
    write_post(path, meta, "body")
    meta, text = read_post(path)
    assert meta["id"] == 1
    assert text == "body"


def test_caption_roundtrip(tmp_path: Path):
    path = tmp_path / "cap.jpg"
    write_caption(path, "cap")
    assert read_caption(path) == "cap\n"


def test_lot_roundtrip(tmp_path: Path):
    path = tmp_path / "lot.json"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lots = [
        {
            "a": 1,
            "b": "x",
            "c": "",
            "timestamp": now,
            "contact:phone": "1",
            "title_en": "t",
            "description_en": "d",
            "title_ru": "t",
            "description_ru": "d",
            "title_ka": "t",
            "description_ka": "d",
        }
    ]
    write_lots(path, lots)
    data = read_lots(path)
    assert data == [
        {
            "a": 1,
            "b": "x",
            "timestamp": now,
            "contact:phone": "1",
            "title_en": "t",
            "description_en": "d",
            "title_ru": "t",
            "description_ru": "d",
            "title_ka": "t",
            "description_ka": "d",
        }
    ]


def test_write_lots_requires_translations(tmp_path: Path):
    path = tmp_path / "lot.json"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lots = [{"timestamp": now, "contact:phone": "1", "title_en": "t"}]
    with pytest.raises(AssertionError):
        write_lots(path, lots)

