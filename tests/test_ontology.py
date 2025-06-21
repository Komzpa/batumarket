from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scan_ontology


def test_collect_ontology(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_ontology, "LOTS_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "FIELDS_FILE", tmp_path / "fields.json")
    monkeypatch.setattr(scan_ontology, "MISPARSED_FILE", tmp_path / "misparsed.json")
    monkeypatch.setattr(scan_ontology, "BROKEN_META_FILE", tmp_path / "broken.json")
    monkeypatch.setattr(scan_ontology, "RAW_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(
        scan_ontology,
        "REVIEW_FILES",
        {f: tmp_path / f"{f}.json" for f in scan_ontology.REVIEW_FIELDS},
    )

    (tmp_path / "sub").mkdir()
    (tmp_path / "a.json").write_text(json.dumps([
        {"a": 1, "b": "x", "title_en": "foo"},
        {"a": 2, "b": "x", "title_en": "bar"}
    ]))
    (tmp_path / "sub" / "b.json").write_text(json.dumps({"b": "y", "c": [1, 2], "title_en": "foo"}))

    scan_ontology.main()

    data = json.loads((tmp_path / "fields.json").read_text())
    assert data["a"] == {"1": 1, "2": 1}
    assert data["b"] == {"x": 2, "y": 1}
    assert data["c"] == {"[1, 2]": 1}

    titles = json.loads((tmp_path / "title_en.json").read_text())
    assert titles == {"foo": 2, "bar": 1}


def test_skip_fields_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_ontology, "LOTS_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "FIELDS_FILE", tmp_path / "fields.json")
    monkeypatch.setattr(scan_ontology, "MISPARSED_FILE", tmp_path / "misparsed.json")
    monkeypatch.setattr(scan_ontology, "BROKEN_META_FILE", tmp_path / "broken.json")
    monkeypatch.setattr(scan_ontology, "RAW_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(
        scan_ontology,
        "REVIEW_FILES",
        {f: tmp_path / f"{f}.json" for f in scan_ontology.REVIEW_FIELDS},
    )

    (tmp_path / "a.json").write_text(json.dumps({
        "timestamp": "now",
        "contact:telegram": "@username",
        "files": ["a.jpg"],
        "other": 5,
        "source:path": "msg.md",
    }))
    (tmp_path / "msg.md").write_text("id: 1\n\nhello", encoding="utf-8")

    scan_ontology.main()

    data = json.loads((tmp_path / "fields.json").read_text())
    assert "timestamp" not in data
    assert "contact:telegram" not in data
    assert "files" not in data
    assert data["other"] == {"5": 1}

    mis = json.loads((tmp_path / "misparsed.json").read_text())
    assert mis[0]["lot"]["contact:telegram"] == "@username"
    assert "Message text:" in mis[0]["input"]


def test_empty_values_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_ontology, "LOTS_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "FIELDS_FILE", tmp_path / "fields.json")
    monkeypatch.setattr(scan_ontology, "MISPARSED_FILE", tmp_path / "misparsed.json")
    monkeypatch.setattr(scan_ontology, "BROKEN_META_FILE", tmp_path / "broken.json")
    monkeypatch.setattr(
        scan_ontology,
        "REVIEW_FILES",
        {f: tmp_path / f"{f}.json" for f in scan_ontology.REVIEW_FIELDS},
    )

    (tmp_path / "a.json").write_text(json.dumps({"a": "", "b": None, "title_en": "x"}))

    scan_ontology.main()

    data = json.loads((tmp_path / "fields.json").read_text())
    assert "a" not in data
    assert "b" not in data


def test_broken_meta_list(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_ontology, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(scan_ontology, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "FIELDS_FILE", tmp_path / "fields.json")
    monkeypatch.setattr(scan_ontology, "MISPARSED_FILE", tmp_path / "misparsed.json")
    monkeypatch.setattr(scan_ontology, "BROKEN_META_FILE", tmp_path / "broken.json")
    monkeypatch.setattr(scan_ontology, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(scan_ontology, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(
        scan_ontology,
        "REVIEW_FILES",
        {f: tmp_path / f"{f}.json" for f in scan_ontology.REVIEW_FIELDS},
    )

    raw = tmp_path / "raw" / "chat" / "2024" / "05"
    raw.mkdir(parents=True)
    (raw / "1.md").write_text("id: 1\nchat: chat\n\ntext")

    lots_dir = tmp_path / "lots" / "chat" / "2024" / "05"
    lots_dir.mkdir(parents=True)
    (lots_dir / "1.json").write_text(json.dumps([{"source:path": "chat/2024/05/1.md"}]))

    scan_ontology.main()

    broken = json.loads((tmp_path / "broken.json").read_text())
    assert broken == [{"chat": "chat", "id": 1}]
