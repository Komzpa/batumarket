import json
import sys
from pathlib import Path
import os
import re
import pytest

os.environ.setdefault("LOG_LEVEL", "INFO")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_site
import similar
import similar_utils
import lot_io


class DummyCfg:
    LANGS = ["en"]
    KEEP_DAYS = 7
    DISPLAY_CURRENCY = "USD"


@pytest.fixture(autouse=True)
def patch_similar(tmp_path, monkeypatch):
    monkeypatch.setattr(similar_utils, "SIMILAR_DIR", tmp_path / "similar")
    monkeypatch.setattr(similar_utils, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(lot_io, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setenv("ALLOW_EMPTY_POSTERS", "1")


@pytest.fixture
def build(monkeypatch):
    def run():
        similar.main()
        build_site.main()

    return run


def test_vectors_generate_similar(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
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

    build()

    html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert "2-0_en.html" in html


def test_vectors_nested_paths(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots" / "chat" / "2024"
    lots_dir.mkdir(parents=True)
    (tmp_path / "media").mkdir()
    vec_dir = tmp_path / "vecs" / "chat" / "2024"
    vec_dir.mkdir(parents=True)

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

    (vec_dir / "1.json").write_text(
        json.dumps([{"id": "chat/2024/1-0", "vec": [1, 0]}])
    )
    (vec_dir / "2.json").write_text(
        json.dumps([{"id": "chat/2024/2-0", "vec": [0.9, 0.1]}])
    )

    build()

    html = (tmp_path / "views" / "chat" / "2024" / "1-0_en.html").read_text()
    assert "2-0_en.html" in html


def test_vector_formatting(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
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

    (lots_dir / "1.json").write_text(json.dumps([
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
        },
    ]))

    vec = [0.123456, -0.987654]
    (vec_dir / "1.json").write_text(json.dumps([{"id": "1-0", "vec": vec}]))

    build()

    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    m = re.search(r"data-embed=\"([^\"]+)\"", cat_html)
    assert m
    raw = m.group(1)
    assert " " not in raw
    parts = raw.strip("[]").split(",")
    assert all(len(p) <= 7 for p in parts)
    assert raw == similar_utils._format_vector(vec)


def test_similar_cache_updates(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(similar_utils, "SIMILAR_DIR", tmp_path / "similar")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    (tmp_path / "vecs").mkdir()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    (lots_dir / "1.json").write_text(json.dumps([
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
    ]))
    (lots_dir / "2.json").write_text(json.dumps([
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
    ]))

    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    (tmp_path / "vecs" / "2.json").write_text(json.dumps([{"id": "2-0", "vec": [0.9, 0.1]}]))

    build()

    (lots_dir / "3.json").write_text(json.dumps([
        {
            "timestamp": now,
            "title_en": "c",
            "description_en": "d",
            "title_ru": "c",
            "description_ru": "d",
            "title_ka": "c",
            "description_ka": "d",
            "files": [],
            "market:deal": "sell_item",
        }
    ]))
    (tmp_path / "vecs" / "3.json").write_text(json.dumps([{"id": "3-0", "vec": [0.8, 0.2]}]))

    build()

    sim_file = similar_utils.SIMILAR_DIR / "1.json"
    data = json.loads(sim_file.read_text())
    cache = {item["id"]: item["similar"] for item in data}
    assert any(s["id"] == "3-0" for s in cache["1-0"])
    assert all("dist" in s for s in cache["1-0"])


def test_similar_cache_invalidates_removed(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(similar_utils, "SIMILAR_DIR", tmp_path / "similar")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "media").mkdir()
    (tmp_path / "vecs").mkdir()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    (lots_dir / "1.json").write_text(json.dumps([
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
    ]))
    (lots_dir / "2.json").write_text(json.dumps([
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
    ]))

    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    (tmp_path / "vecs" / "2.json").write_text(json.dumps([{"id": "2-0", "vec": [0.9, 0.1]}]))

    build()

    (lots_dir / "2.json").unlink()
    (tmp_path / "vecs" / "2.json").unlink()

    build()

    sim_file = similar_utils.SIMILAR_DIR / "1.json"
    data = json.loads(sim_file.read_text())
    cache = {item["id"]: item["similar"] for item in data}
    assert all(s["id"] != "2-0" for s in cache["1-0"])


def test_similar_titles_use_language(tmp_path, monkeypatch, build):
    class Cfg:
        LANGS = ["en", "ru"]
        KEEP_DAYS = 7

    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(similar_utils, "SIMILAR_DIR", tmp_path / "similar")
    monkeypatch.setattr(build_site, "load_config", lambda: Cfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    vec_dir = tmp_path / "vecs"
    vec_dir.mkdir()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    (lots_dir / "1.json").write_text(
        json.dumps([
            {
                "timestamp": now,
                "title_en": "hello",
                "title_ru": "привет",
                "title_ka": "hello",
                "description_en": "d",
                "description_ru": "d",
                "description_ka": "d",
                "files": ["a.jpg"],
                "market:deal": "sell_item",
            }
        ])
    )
    (lots_dir / "2.json").write_text(
        json.dumps([
            {
                "timestamp": now,
                "title_en": "world",
                "title_ru": "мир",
                "title_ka": "world",
                "description_en": "d",
                "description_ru": "d",
                "description_ka": "d",
                "files": ["b.jpg"],
                "market:deal": "sell_item",
            }
        ])
    )

    (vec_dir / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    (vec_dir / "2.json").write_text(json.dumps([{"id": "2-0", "vec": [0.9, 0.1]}]))

    build()

    html_en = (tmp_path / "views" / "1-0_en.html").read_text()
    html_ru = (tmp_path / "views" / "1-0_ru.html").read_text()
    assert "world" in html_en
    assert "мир" in html_ru
