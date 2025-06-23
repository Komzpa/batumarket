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
    monkeypatch.setattr(clean_data, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(clean_data, "load_config", lambda: DummyCfg())

    cutoff = datetime.now(timezone.utc) - timedelta(days=DummyCfg.KEEP_DAYS + 1)
    recent = datetime.now(timezone.utc)

    raw_old = clean_data.RAW_DIR / "chat" / "2024" / "05" / "1.md"
    raw_old.parent.mkdir(parents=True)
    raw_old.write_text(f"id: 1\ndate: {cutoff.isoformat()}\n\nold")

    raw_new = clean_data.RAW_DIR / "chat" / "2024" / "05" / "2.md"
    raw_new.parent.mkdir(parents=True, exist_ok=True)
    raw_new.write_text(f"id: 2\ndate: {recent.isoformat()}\n\nnew")

    # directory that becomes empty after cleanup
    raw_empty = clean_data.RAW_DIR / "oldchat" / "2024" / "05" / "1.md"
    raw_empty.parent.mkdir(parents=True)
    raw_empty.write_text(f"id: 3\ndate: {cutoff.isoformat()}\n\nold")

    media_dir = clean_data.MEDIA_DIR / "chat" / "2024" / "05"
    media_dir.mkdir(parents=True)
    img_old = media_dir / "a.jpg"
    img_old.write_bytes(b"img")
    (media_dir / "a.jpg.md").write_text(f"message_id:1\ndate: {cutoff.isoformat()}\n")

    img_new = media_dir / "b.jpg"
    img_new.write_bytes(b"img2")
    (media_dir / "b.jpg.md").write_text(f"message_id:2\ndate:{recent.isoformat()}\n")
    (media_dir / "b.caption.json").write_text('{"caption_en": "cap"}')

    media_empty_dir = clean_data.MEDIA_DIR / "oldchat" / "2024" / "05"
    media_empty_dir.mkdir(parents=True)
    img_old2 = media_empty_dir / "c.jpg"
    img_old2.write_bytes(b"img")
    (media_empty_dir / "c.jpg.md").write_text(f"message_id:3\ndate: {cutoff.isoformat()}\n")

    lot_dir = clean_data.LOTS_DIR / "chat" / "2024" / "05"
    lot_dir.mkdir(parents=True)
    old_lot = lot_dir / "1.json"
    old_lot.write_text(
        json.dumps([
            {
                "_id": "1",
                "source:path": "chat/2024/05/1.md",
                "title_en": "t",
                "description_en": "d",
                "title_ru": "t",
                "description_ru": "d",
                "title_ka": "t",
                "description_ka": "d",
            }
        ])
    )
    new_lot = lot_dir / "2.json"
    new_lot.write_text(
        json.dumps([
            {
                "_id": "2",
                "source:path": "chat/2024/05/2.md",
                "title_en": "t",
                "description_en": "d",
                "title_ru": "t",
                "description_ru": "d",
                "title_ka": "t",
                "description_ka": "d",
            }
        ])
    )

    lot_empty_dir = clean_data.LOTS_DIR / "oldchat" / "2024" / "05"
    lot_empty_dir.mkdir(parents=True)
    empty_lot = lot_empty_dir / "3.json"
    empty_lot.write_text(
        json.dumps([
            {
                "_id": "3",
                "source:path": "oldchat/2024/05/1.md",
                "title_en": "t",
                "description_en": "d",
                "title_ru": "t",
                "description_ru": "d",
                "title_ka": "t",
                "description_ka": "d",
            }
        ])
    )

    vec_dir = clean_data.VEC_DIR / "chat" / "2024" / "05"
    vec_dir.mkdir(parents=True)
    v_old = vec_dir / "1.json"
    v_old.write_text("oldvec")
    v_new = vec_dir / "2.json"
    v_new.write_text("newvec")
    orphan_dir = clean_data.VEC_DIR / "orphan" / "2024" / "05"
    orphan_dir.mkdir(parents=True)
    v_orphan = orphan_dir / "3.json"
    v_orphan.write_text("orphan")

    clean_data.main()

    assert not raw_old.exists()
    assert raw_new.exists()
    assert not raw_empty.parent.exists()
    assert not img_old.exists()
    assert not img_old.with_suffix(".md").exists()
    assert img_new.exists()
    assert not media_empty_dir.exists()
    assert not old_lot.exists()
    assert new_lot.exists()
    assert not lot_empty_dir.exists()
    assert not v_old.exists()
    assert v_new.exists()
    assert not v_orphan.exists()
    assert not orphan_dir.exists()


def test_clean_data_removes_missing_translations(tmp_path, monkeypatch):
    monkeypatch.setattr(clean_data, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(clean_data, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(clean_data, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(clean_data, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(clean_data, "load_config", lambda: DummyCfg())

    lot_dir = clean_data.LOTS_DIR / "chat" / "2024" / "05"
    lot_dir.mkdir(parents=True)
    bad = lot_dir / "1.json"
    bad.write_text(json.dumps([{"_id": "1"}]))

    clean_data.main()

    assert not bad.exists()


def test_clean_data_keeps_fraud_without_translations(tmp_path, monkeypatch):
    monkeypatch.setattr(clean_data, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(clean_data, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(clean_data, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(clean_data, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(clean_data, "load_config", lambda: DummyCfg())

    lot_dir = clean_data.LOTS_DIR / "chat" / "2024" / "05"
    lot_dir.mkdir(parents=True)
    flagged = lot_dir / "1.json"
    flagged.write_text(json.dumps([{"_id": "1", "fraud": "spam"}]))

    clean_data.main()

    assert flagged.exists()
