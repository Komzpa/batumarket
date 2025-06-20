import sys
import json
import types
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

class DummyCfg:
    KEEP_DAYS = 7

sys.modules["config"] = types.ModuleType("config")
sys.modules["config"].KEEP_DAYS = DummyCfg.KEEP_DAYS

import clean_data

def test_clean_data(tmp_path, monkeypatch):
    monkeypatch.setattr(clean_data, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(clean_data, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(clean_data, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(clean_data, "load_config", lambda: DummyCfg())

    cutoff = datetime.now(timezone.utc) - timedelta(days=DummyCfg.KEEP_DAYS + 1)
    recent = datetime.now(timezone.utc)

    raw_old = clean_data.RAW_DIR / "chat" / "2024" / "05" / "1.md"
    raw_old.parent.mkdir(parents=True)
    raw_old.write_text(f"id: 1\ndate: {cutoff.isoformat()}\n\nold")

    raw_new = clean_data.RAW_DIR / "chat" / "2024" / "05" / "2.md"
    raw_new.parent.mkdir(parents=True, exist_ok=True)
    raw_new.write_text(f"id: 2\ndate: {recent.isoformat()}\n\nnew")

    media_dir = clean_data.MEDIA_DIR / "chat" / "2024" / "05"
    media_dir.mkdir(parents=True)
    img_old = media_dir / "a.jpg"
    img_old.write_bytes(b"img")
    (media_dir / "a.jpg.md").write_text(f"message_id:1\ndate: {cutoff.isoformat()}\n")

    img_new = media_dir / "b.jpg"
    img_new.write_bytes(b"img2")
    (media_dir / "b.jpg.md").write_text(f"message_id:2\ndate:{recent.isoformat()}\n")
    (media_dir / "b.caption.md").write_text("cap")

    lot_dir = clean_data.LOTS_DIR / "chat" / "2024" / "05"
    lot_dir.mkdir(parents=True)
    old_lot = lot_dir / "1.json"
    old_lot.write_text(json.dumps([{"_id": "1", "source:path": "chat/2024/05/1.md"}]))
    new_lot = lot_dir / "2.json"
    new_lot.write_text(json.dumps([{"_id": "2", "source:path": "chat/2024/05/2.md"}]))

    clean_data.main()

    assert not raw_old.exists()
    assert raw_new.exists()
    assert not img_old.exists()
    assert not img_old.with_suffix(".md").exists()
    assert img_new.exists()
    assert not old_lot.exists()
    assert new_lot.exists()
