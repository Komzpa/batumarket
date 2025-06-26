from pathlib import Path
import json
import sys
import os
import re
import pytest

os.environ.setdefault("LOG_LEVEL", "INFO")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_site
import price_utils
import similar_utils
import similar
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


def test_build_site_creates_pages(tmp_path, monkeypatch, build):
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
    from datetime import datetime, timezone
    (tmp_path / "vecs").mkdir()
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
    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    build()

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
    assert 'data-embed' in cat_html
    assert (tmp_path / "views" / "static" / "site.js").exists()
    assert (tmp_path / "views" / "static" / "style.css").exists()

    lot_html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert 'window.currentLot' in lot_html


def test_handles_list_fields(tmp_path, monkeypatch, build):
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
    from datetime import datetime, timezone
    (tmp_path / "vecs").mkdir()
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
    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))

    build()

    assert (tmp_path / "views" / "1-0_en.html").exists()


def test_author_fallback(tmp_path, monkeypatch, build):
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
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "vecs").mkdir()
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
    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))

    build()

    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    assert "@poster" in cat_html


def test_build_site_skips_moderated(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
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

    build()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_build_site_skips_misparsed(tmp_path, monkeypatch, build):
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

    build()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_build_site_skips_missing_titles(tmp_path, monkeypatch, build):
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

    build()

    assert not (tmp_path / "views" / "1-0_en.html").exists()


def test_images_and_empty_values(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (tmp_path / "vecs").mkdir()
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
            "files": ["a.jpg"],
            "title_ka": "x",
            "description_ka": "d",
            "market:deal": "sell_item",
            "extra": "",
            "other": None,
        }
    ]))
    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))

    build()

    assert (tmp_path / "views" / "media" / "a.jpg").exists()
    html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert "extra" not in html
    assert "other" not in html



def test_page_headers_and_orig_open(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
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
                "contact:telegram": "@u",
                "source:path": "1.md",
            },
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
                "contact:telegram": "@u",
            },
        ])
    )
    (raw_dir / "1.md").write_text("id: 1\n\ntext", encoding="utf-8")
    (vec_dir / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))
    (vec_dir / "2.json").write_text(json.dumps([{"id": "1-1", "vec": [0.9, 0.1]}]))

    build()

    html = (tmp_path / "views" / "1-0_en.html").read_text()
    assert '<details class="orig-text" open>' in html
    assert '<h2>Similar items</h2>' in html
    assert '<h2>More by this user</h2>' in html
    assert 'class="more-user similar carousel"' in html

def test_drop_lots_without_vectors(tmp_path, monkeypatch, build):
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
        },
    ]))

    (vec_dir / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))

    build()

    assert (tmp_path / "views" / "1-0_en.html").exists()
    assert not (tmp_path / "views" / "1-1_en.html").exists()
    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    assert "1-0_en.html" in cat_html
    assert "1-1_en.html" not in cat_html


def test_category_html_parses(tmp_path, monkeypatch, build):
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
    (tmp_path / "vecs" / "1.json").write_text(json.dumps([{"id": "1-0", "vec": [1, 0]}]))

    build()

    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    import html5lib

    parser = html5lib.HTMLParser(strict=True)
    parser.parse(cat_html)
    assert parser.errors == []


def test_ai_price_fallback(tmp_path, monkeypatch, build):
    monkeypatch.setattr(build_site, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(build_site, "VIEWS_DIR", tmp_path / "views")
    monkeypatch.setattr(build_site, "TEMPLATES", Path("templates"))
    monkeypatch.setattr(build_site, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(build_site, "ONTOLOGY", tmp_path / "ont.json")
    monkeypatch.setattr(build_site, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(build_site, "load_config", lambda: DummyCfg())

    lots_dir = tmp_path / "lots"
    lots_dir.mkdir()
    (tmp_path / "vecs").mkdir()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (lots_dir / "1.json").write_text(
        json.dumps([
            {
                "timestamp": now,
                "title_en": "ref", "description_en": "d",
                "title_ru": "ref", "description_ru": "d",
                "title_ka": "ref", "description_ka": "d",
                "files": [], "market:deal": "sell_item",
                "price": 100, "price:currency": "USD"
            },
            {
                "timestamp": now,
                "title_en": "pred", "description_en": "d",
                "title_ru": "pred", "description_ru": "d",
                "title_ka": "pred", "description_ka": "d",
                "files": [], "market:deal": "sell_item",
                "price:currency": "USD"
            }
        ])
    )
    (tmp_path / "vecs" / "1.json").write_text(
        json.dumps([
            {"id": "1-0", "vec": [1.0, 0.0]},
            {"id": "1-1", "vec": [1.0, 0.0]}
        ])
    )

    build()

    cat_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    assert cat_html.count("100") >= 2


def test_sell_item_subcategories(tmp_path, monkeypatch, build):
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
                "title_en": "phone",
                "description_en": "d",
                "title_ru": "phone",
                "description_ru": "d",
                "title_ka": "phone",
                "description_ka": "d",
                "files": [],
                "market:deal": "sell_item",
                "item:type": "smartphone",
                "price": 100,
                "price:currency": "USD",
            },
            {
                "timestamp": now,
                "title_en": "laptop",
                "description_en": "d",
                "title_ru": "laptop",
                "description_ru": "d",
                "title_ka": "laptop",
                "description_ka": "d",
                "files": [],
                "market:deal": "sell_item",
                "item:type": "laptop",
                "price": 200,
                "price:currency": "USD",
            },
        ])
    )
    (vec_dir / "1.json").write_text(
        json.dumps([
            {"id": "1-0", "vec": [1.0, 0.0]},
            {"id": "1-1", "vec": [0.0, 2.0]},
        ])
    )

    build()

    assert (tmp_path / "views" / "deal" / "sell_item.smartphone_en.html").exists()
    assert (tmp_path / "views" / "deal" / "sell_item.laptop_en.html").exists()
    root_html = (tmp_path / "views" / "deal" / "sell_item_en.html").read_text()
    assert "smartphone" in root_html
    assert "laptop" in root_html


def test_category_stats_with_centroid(tmp_path):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ts = now.isoformat()
    lots = [
        {
            "_id": "1-0",
            "timestamp": ts,
            "market:deal": "sell_item",
            "item:type": "smartphone",
            "price": 100,
            "price:currency": "USD",
        }
    ]
    embeds = {"1-0": [1.0, 0.0]}
    price_utils.prepare_price_fields(lots, {"USD": 1.0}, "USD")
    cats, stats, _ = build_site._categorise(lots, ["en"], 7, embeds)
    assert "sell_item.smartphone" in cats
    stat = stats["sell_item.smartphone"]
    assert stat["price_typical"] == 100
    assert stat["price_min"] == 100
    assert stat["price_max"] == 100
    assert stat["last_dt"] == now
    assert stat["centroid"] == [1.0, 0.0]


def test_recent_user_count():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    recent_ts = (now - timedelta(days=1)).isoformat()
    old_ts = (now - timedelta(days=8)).isoformat()

    lots = [
        {
            "_id": "1",
            "timestamp": recent_ts,
            "market:deal": "sell_item",
            "contact:telegram": "alice",
        },
        {
            "_id": "2",
            "timestamp": old_ts,
            "market:deal": "sell_item",
            "contact:telegram": "bob",
        },
    ]

    cats, stats, _ = build_site._categorise(lots, ["en"], 7, {})
    assert "sell_item" in cats
    stat = stats["sell_item"]
    assert stat["recent"] == 1
    assert len(stat["recent_users"]) == 1
    assert len(stat["users"]) == 2
