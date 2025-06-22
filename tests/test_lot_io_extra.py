import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lot_io import get_seller, get_timestamp
from lot_io import make_lot_id, parse_lot_id, embedding_path


def test_get_seller_priority():
    lot = {
        "contact:viber": "viberuser",
        "contact:phone": "+995123",
        "seller": "manual"
    }
    # phone should take precedence over others
    assert get_seller(lot) == "+995123"


def test_get_timestamp_parsing():
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=1)).isoformat()
    past = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    lot_past = {"timestamp": past}
    lot_future = {"timestamp": future}
    lot_bad = {"timestamp": "not-a-date"}
    assert get_timestamp(lot_past) is not None
    assert get_timestamp(lot_future) is None
    assert get_timestamp(lot_bad) is None


def test_id_roundtrip():
    rel = Path("chat/2025/06/1234")
    lot_id = make_lot_id(rel, 2)
    back_rel, idx = parse_lot_id(lot_id)
    assert back_rel == rel
    assert idx == 2


def test_embedding_path():
    lot_file = Path("data/lots/chat/2025/06/1.json")
    vec = embedding_path(lot_file, Path("v"), Path("data/lots"))
    assert vec == Path("v/chat/2025/06/1.json")
