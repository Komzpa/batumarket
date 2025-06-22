from pathlib import Path
import json
import sys
import os

os.environ.setdefault("LOG_LEVEL", "INFO")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_site


class DummyCfg:
    LANGS = ["en"]
    KEEP_DAYS = 7


def test_build_site_creates_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "hello",
            "description_en": "d",
            "title_ru": "hello",
            "description_ru": "d",
            "title_ka": "hello",
            "description_ka": "d",
            "files": [],
            "market:deal": "sell_item",
            "contact:telegram": "@user",
        }
    ]))

    build_site.main()

    assert (tmp_path / "views" / "1-0_en.html").exists()
    index = tmp_path / "views" / "index_en.html"
    assert index.exists()
    idx_html = index.read_text()
    assert "sell_item" in idx_html
    cat_page = tmp_path / "views" / "deal" / "sell_item_en.html"
    assert cat_page.exists()
    cat_html = cat_page.read_text()
    assert "hello" in cat_html
    assert "1-0_en.html" in cat_html
    assert (tmp_path / "views" / "static" / "site.js").exists()
    assert (tmp_path / "views" / "static" / "style.css").exists()


def test_handles_list_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "hello",
            "description_en": "d",
            "title_ru": "hello",
            "description_ru": "d",
            "title_ka": "hello",
            "description_ka": "d",
            "files": [],
            "market:deal": ["sell_item", "other"],
            "contact:telegram": ["@user", "@other"],
        }
    ]))

    build_site.main()

    assert (tmp_path / "views" / "1-0_en.html").exists()


def test_author_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "hello",
            "description_en": "d",
            "title_ru": "hello",
            "description_ru": "d",
            "title_ka": "hello",
            "description_ka": "d",
            "files": [],
            "market:deal": "sell_item",
            "source:author:telegram": "@poster",
            "source:author:name": "Poster",
        }
    ]))

    build_site.main()

    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    assert "@poster" in cat_html


def test_build_site_skips_moderated(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(build_site, "RAW_DIR", raw_dir)
    lots_dir.mkdir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (raw_dir / "1.md").write_text("id: 1\n\nspam", encoding="utf-8")
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "hello",
            "description_en": "d",
            "title_ru": "hello",
            "description_ru": "d",
            "title_ka": "hello",
            "description_ka": "d",
            "files": [],
            "market:deal": "sell_item",
            "source:path": "1.md",
        }
    ]))

    monkeypatch.setattr(build_site, "should_skip_message", lambda m, t: True)

    build_site.main()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_build_site_skips_misparsed(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "bad",
            "description_en": "d",
            "title_ru": "bad",
            "description_ru": "d",
            "title_ka": "bad",
            "description_ka": "d",
            "files": [],
            "market:deal": "sell_item",
            "contact:telegram": "@username",
        }
    ]))

    build_site.main()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_build_site_skips_missing_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "files": [],
            "market:deal": "sell_item",
            "contact:telegram": "@real"
        }
    ]))

    build_site.main()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_images_and_empty_values(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    img = media_dir / "a.jpg"
    img.write_bytes(b"img")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "x",
            "description_en": "d",
            "title_ru": "x",
            "description_ru": "d",
            "title_ka": "x",
            "description_ka": "d",
            "files": ["a.jpg"],
            "market:deal": "sell_item",
            "extra": "",
            "other": None,
        }
    ]))

    build_site.main()

    assert (tmp_path / "views" / "media" / "a.jpg").exists()
    html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert "extra" not in html
    assert "other" not in html


def test_vectors_generate_similar(tmp_path, monkeypatch):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    vec_dir = tmp_path / "vecs"
    vec_dir.mkdir()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    (lots_dir / "1.json").write_text(
        json.dumps([
            {
                "timestamp": now,
                "title_en": "a",
                "description_en": "d",
                "title_ru": "a",
                "description_ru": "d",
                "title_ka": "a",
                "description_ka": "d",
                "files": [],
                "market:deal": "sell_item",
            }
        ])
    )
    (lots_dir / "2.json").write_text(
        json.dumps([
            {
                "timestamp": now,
                "title_en": "b",
                "description_en": "d",
                "title_ru": "b",
                "description_ru": "d",
                "title_ka": "b",
                "description_ka": "d",
                "files": [],
                "market:deal": "sell_item",
            }
        ])
    )

    (vec_dir / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    (vec_dir / "2.json").write_text(json.dumps([{"id": "2-0", "vec": [0.9, 0.1]}]))

    build_site.main()

    html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert "2-0_en.html" in html
