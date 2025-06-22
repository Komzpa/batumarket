import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from post_io import get_contact, get_timestamp, is_broken_meta, iter_broken_posts


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


def test_is_broken_meta():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ok = {"id": 1, "chat": "c", "date": now, "sender_name": "x"}
    assert not is_broken_meta(ok)
    assert is_broken_meta({"chat": "c", "date": now, "sender_name": "x"})
    assert is_broken_meta({"id": 1, "chat": "c", "sender_name": "x"})
    assert is_broken_meta({"id": 1, "chat": "c", "date": now})


def test_iter_broken_posts(tmp_path):
    raw_dir = tmp_path / "raw"
    msg_dir = raw_dir / "chat" / "2024" / "05"
    msg_dir.mkdir(parents=True)
    (msg_dir / "1.md").write_text("id: 1\nchat: chat\n\n")
    (msg_dir / "2.md").write_text(
        "id: 2\nchat: chat\ndate: 2024-05-01T00:00:00+00:00\nsender_name: x\n\ntext"
    )

    entries = dict(iter_broken_posts(raw_dir))
    assert ("chat", 1) in entries
    assert ("chat", 2) not in entries

