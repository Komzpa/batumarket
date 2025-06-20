from pathlib import Path
import json
import sys
import os

os.environ.setdefault("LOG_LEVEL", "INFO")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_site


class DummyCfg:
    LANGS = ["en"]


def test_build_site_creates_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": "2024-05-20T00:00:00",
            "title_en": "hello",
            "files": []
        }
    ]))

    build_site.main()

    assert (tmp_path / "views" / "1-0.html").exists()
    assert (tmp_path / "views" / "index.html").exists()
