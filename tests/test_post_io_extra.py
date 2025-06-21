import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from post_io import get_contact, get_timestamp


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

