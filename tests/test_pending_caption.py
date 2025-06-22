import sys
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pending_caption


def test_list_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_caption, "MEDIA_DIR", tmp_path / "media")

    img = pending_caption.MEDIA_DIR / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"img")

    pending_caption.main()
    out = capsys.readouterr().out
    assert out == str(img) + "\0"


def test_skip_existing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_caption, "MEDIA_DIR", tmp_path / "media")

    img = pending_caption.MEDIA_DIR / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"img")
    (img.with_suffix(".caption.md")).write_text("cap")

    pending_caption.main()
    out = capsys.readouterr().out
    assert out == ""


def test_skip_due_to_moderation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pending_caption, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(pending_caption, "RAW_DIR", tmp_path / "raw")

    img = pending_caption.MEDIA_DIR / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"img")
    meta = img.with_suffix(".md")
    meta.write_text("message_id: 1")

    msg = pending_caption.RAW_DIR / "chat" / "2024" / "05" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("sender_username: m_s_help_bot\n\nspam")

    pending_caption.main()
    out = capsys.readouterr().out
    assert out == ""


def test_cli_runs(tmp_path):
    media_dir = tmp_path / "data" / "media" / "chat"
    media_dir.mkdir(parents=True)
    (media_dir / "img.jpg").write_bytes(b"d")

    script = Path(__file__).resolve().parents[1] / "scripts" / "pending_caption.py"
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
    expected = str(Path("data/media/chat/img.jpg")) + "\0"
    assert out.stdout == expected
    assert out.returncode == 0

