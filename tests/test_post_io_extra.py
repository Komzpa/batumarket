import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from post_io import get_contact, get_timestamp, write_post, read_post
import ast
import pytest


def test_get_contact_priority():
    meta = {
        "sender_username": "user",
        "sender_phone": "+123",
        "sender_name": "name",
    }
    # phone should take precedence over others
    assert get_contact(meta) == "+123"


def test_get_timestamp_parsing():
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=1)).isoformat()
    past = (now - timedelta(days=1)).replace(microsecond=0).isoformat()

    meta_past = {"date": past}
    meta_future = {"date": future}
    meta_bad = {"date": "bad"}

    assert get_timestamp(meta_past) is not None
    assert get_timestamp(meta_future) is None
    assert get_timestamp(meta_bad) is None


def test_write_post_rejects_header_in_body(tmp_path: Path):
    path = tmp_path / "post.md"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta = {"id": 1, "chat": "x", "date": now, "sender_name": "u"}
    with pytest.raises(AssertionError):
        write_post(path, meta, "id: 2\ntext")


def test_read_post_merges_files(tmp_path: Path):
    path = tmp_path / "post.md"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    content = (
        f"id: 1\nchat: x\ndate: {now}\nfiles: ['a.jpg']\n\n"
        f"id: 1\nchat: x\ndate: {now}\nfiles: ['b.jpg']\n\nbody"
    )
    path.write_text(content)
    meta, text = read_post(path)
    assert ast.literal_eval(meta.get("files", "[]")) == ["a.jpg", "b.jpg"]
    assert text == "body"


def test_read_post_mismatch_raises(tmp_path: Path):
    path = tmp_path / "post.md"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    content = (
        f"id: 1\nchat: x\ndate: {now}\n\n"
        f"id: 2\nchat: x\ndate: {now}\n\n"
    )
    path.write_text(content)
    with pytest.raises(AssertionError):
        read_post(path)

