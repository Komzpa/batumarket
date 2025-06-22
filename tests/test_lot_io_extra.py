import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lot_io import get_seller, get_timestamp
from lot_io import make_lot_id, parse_lot_id, embedding_path, iter_lot_files


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


def test_iter_lot_files_order(tmp_path):
    root = tmp_path / "lots"
    root.mkdir()
    a = root / "a.json"
    b = root / "b.json"
    a.write_text("[]")
    b.write_text("[]")
    os.utime(a, (1, 1))
    os.utime(b, (2, 2))

    files = iter_lot_files(root, newest_first=True)
    assert files == [b, a]

    files_default = iter_lot_files(root)
    assert files_default == [a, b]
