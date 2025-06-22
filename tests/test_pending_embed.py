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
    path.write_text(json.dumps([{"a": 1}]))

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
    path.write_text(json.dumps([{"a": 1}, {"a": 2}]))

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
    assert out.stdout == "data/lots/1.json\0"
    assert out.returncode == 0
