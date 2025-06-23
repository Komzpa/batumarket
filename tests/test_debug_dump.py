import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import debug_dump


def test_parse_url():
    lot, lang = debug_dump.parse_url(
        "http://example.com/chat/2025/06/1234-0_ru.html"
    )
    assert lot == "chat/2025/06/1234-0"
    assert lang == "ru"


def test_guess_source_from_lot():
    chat, mid = debug_dump.guess_source_from_lot("chat/2025/06/1234-0")
    assert chat == "chat"
    assert mid == 1234


def test_run_tg_fetch_includes_stderr(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_MODE", raising=False)

    class DummyProc:
        stdout = "out"
        stderr = "err"

    def dummy_run(*_a, **_k):
        return DummyProc()

    monkeypatch.setattr(debug_dump.subprocess, "run", dummy_run)
    monkeypatch.chdir(tmp_path)
    out = debug_dump.run_tg_fetch("chat", 1)
    assert "out" in out
    assert "err" in out


def test_delete_files(tmp_path, monkeypatch):
    lot_id = "chat/2024/01/1"

    lots_dir = tmp_path / "lots"
    vec_dir = tmp_path / "vec"
    raw_dir = tmp_path / "raw"
    media_dir = tmp_path / "media"
    lots_dir.mkdir(parents=True)
    vec_dir.mkdir()
    raw_dir.mkdir()
    media_dir.mkdir()

    monkeypatch.setattr(debug_dump, "LOTS_DIR", lots_dir)
    monkeypatch.setattr(debug_dump, "VEC_DIR", vec_dir)
    monkeypatch.setattr(debug_dump, "RAW_DIR", raw_dir)
    monkeypatch.setattr(debug_dump, "MEDIA_DIR", media_dir)

    lot_file = lots_dir / f"{lot_id}.json"
    lot_file.parent.mkdir(parents=True, exist_ok=True)
    lot_file.write_text('{"source:path": "raw.md", "files": ["f.jpg"]}')

    vec_file = vec_dir / f"{lot_id}.json"
    vec_file.parent.mkdir(parents=True, exist_ok=True)
    vec_file.write_text("vec")

    raw_path = raw_dir / "raw.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("raw")

    img = media_dir / "f.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_text("bin")
    img_md = img.with_suffix(".md")
    img_md.write_text("meta")
    img_cap = img.with_suffix(".caption.json")
    img_cap.write_text('{"caption_en": "cap"}')

    debug_dump.delete_files(lot_id)

    assert not lot_file.exists()
    assert not vec_file.exists()
    assert not raw_path.exists()
    assert not img.exists()
    assert not img_md.exists()
    assert not img_cap.exists()


def test_skip_fetch_when_cached(tmp_path, monkeypatch):
    lot_id = "chat/2024/01/1"

    monkeypatch.setattr(debug_dump, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(debug_dump, "VEC_DIR", tmp_path / "vec")
    monkeypatch.setattr(debug_dump, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(debug_dump, "MEDIA_DIR", tmp_path / "media")

    lot_file = debug_dump.LOTS_DIR / f"{lot_id}.json"
    lot_file.parent.mkdir(parents=True, exist_ok=True)
    lot_file.write_text('{"source:path": "raw.md"}')

    raw_path = debug_dump.RAW_DIR / "raw.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("id: 1\n\ntext")

    def fail_fetch(*_a, **_k):
        raise AssertionError("called")

    monkeypatch.setattr(debug_dump, "run_tg_fetch", fail_fetch)
    url = "http://example.com/chat/2024/01/1-0_en.html"
    debug_dump.main([url])


def test_moderation_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_dump, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(debug_dump, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(debug_dump, "VEC_DIR", tmp_path / "vec")
    monkeypatch.setattr(debug_dump, "MEDIA_DIR", tmp_path / "media")

    lot_id = "chat/2024/01/1"
    lot_path = debug_dump.LOTS_DIR / f"{lot_id}.json"
    lot_path.parent.mkdir(parents=True, exist_ok=True)
    lot_path.write_text('[{"source:path": "1.md", "title_en": "t", "description_en": "d", "title_ru": "t", "description_ru": "d", "title_ka": "t", "description_ka": "d"}]')

    raw_path = debug_dump.RAW_DIR / "1.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("id: 1\n\nmdma")

    summary = debug_dump.moderation_summary(lot_id)
    assert "banned phrase" in summary
    assert "vectors: missing" in summary

    vec_path = debug_dump.VEC_DIR / f"{lot_id}.json"
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    vec_path.write_text('[{"id": "x", "vec": [1]}]')
    summary = debug_dump.moderation_summary(lot_id)
    assert "vectors: ok" in summary

