import sys
import json
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pending_embed
from serde_utils import load_json


def test_upgrade_legacy_format(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_embed, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(pending_embed, "VEC_DIR", tmp_path / "vecs")

    path = pending_embed.LOTS_DIR / "1.json"
    path.parent.mkdir(parents=True)
    lot = {
        "timestamp": "2024-05-01T00:00:00+00:00",
        "title_en": "t",
        "description_en": "d",
        "title_ru": "t",
        "description_ru": "d",
        "title_ka": "t",
        "description_ka": "d",
        "contact:telegram": "@u",
    }
    path.write_text(json.dumps([lot]))

    vec = pending_embed.VEC_DIR / "1.json"
    vec.parent.mkdir(parents=True)
    vec.write_text(json.dumps({"id": "x", "vec": [1]}))

    pending_embed.main()
    out = capsys.readouterr().out
    assert out == ""
    data = load_json(vec)
    assert isinstance(data, list)
    assert data[0]["id"] == "x"


def test_vector_count_mismatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_embed, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(pending_embed, "VEC_DIR", tmp_path / "vecs")

    path = pending_embed.LOTS_DIR / "1.json"
    path.parent.mkdir(parents=True)
    lot1 = {
        "timestamp": "2024-05-01T00:00:00+00:00",
        "title_en": "t1",
        "description_en": "d",
        "title_ru": "t1",
        "description_ru": "d",
        "title_ka": "t1",
        "description_ka": "d",
        "contact:telegram": "@u",
    }
    lot2 = {
        "timestamp": "2024-05-01T00:00:00+00:00",
        "title_en": "t2",
        "description_en": "d",
        "title_ru": "t2",
        "description_ru": "d",
        "title_ka": "t2",
        "description_ka": "d",
        "contact:telegram": "@u",
    }
    path.write_text(json.dumps([lot1, lot2]))

    vec = pending_embed.VEC_DIR / "1.json"
    vec.parent.mkdir(parents=True)
    vec.write_text(json.dumps([{"id": "x", "vec": [1]}]))

    pending_embed.main()
    out = capsys.readouterr().out
    assert out == str(path) + "\0"
    assert not vec.exists()


def test_cli_runs(tmp_path):
    """The script should run standalone without PYTHONPATH."""
    lots_dir = tmp_path / "data" / "lots"
    lots_dir.mkdir(parents=True)
    (lots_dir / "1.json").write_text("[]")
    (tmp_path / "data" / "vectors").mkdir(parents=True)

    script = Path(__file__).resolve().parents[1] / "scripts" / "pending_embed.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    out = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout == ""
    assert out.returncode == 0


def test_skip_due_to_moderation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_embed, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(pending_embed, "VEC_DIR", tmp_path / "vecs")
    monkeypatch.setattr(pending_embed, "RAW_DIR", tmp_path / "raw")

    lot_dir = pending_embed.LOTS_DIR
    lot_dir.mkdir(parents=True)
    now = "2024-05-01T00:00:00+00:00"
    lot = {
        "timestamp": now,
        "title_en": "t",
        "description_en": "d",
        "title_ru": "t",
        "description_ru": "d",
        "title_ka": "t",
        "description_ka": "d",
        "contact:telegram": "@u",
        "source:path": "chat/2024/05/1.md",
    }
    path = lot_dir / "1.json"
    path.write_text(json.dumps([lot]))

    raw = pending_embed.RAW_DIR / "chat" / "2024" / "05" / "1.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("sender_username: m_s_help_bot\n\nspam")

    pending_embed.main()
    out = capsys.readouterr().out
    assert out == ""
