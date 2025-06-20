from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scan_ontology


def test_collect_ontology(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_ontology, "LOTS_DIR", tmp_path)
    monkeypatch.setattr(scan_ontology, "OUTPUT_FILE", tmp_path / "out.json")

    (tmp_path / "sub").mkdir()
    (tmp_path / "a.json").write_text(json.dumps([
        {"a": 1, "b": "x"},
        {"a": 2, "b": "x"}
    ]))
    (tmp_path / "sub" / "b.json").write_text(json.dumps({"b": "y", "c": [1, 2]}))

    scan_ontology.main()

    data = json.loads((tmp_path / "out.json").read_text())
    assert data["a"] == {"1": 1, "2": 1}
    assert data["b"] == {"x": 2, "y": 1}
    assert data["c"] == {"[1, 2]": 1}
