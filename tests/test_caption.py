from pathlib import Path
import os
import sys
import json
import types

# Provide a minimal ``openai`` stub before importing the module under test.
dummy_openai = types.ModuleType("openai")
dummy_openai.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda *a, **k: None))
sys.modules["openai"] = dummy_openai

# Minimal config stub required by ``caption`` module.
dummy_cfg = types.ModuleType("config")
dummy_cfg.OPENAI_KEY = ""
sys.modules["config"] = dummy_cfg

# Ensure info level logs for tests
os.environ["LOG_LEVEL"] = "INFO"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import caption
from log_utils import LOGFILE


def test_caption_file_writes(tmp_path, monkeypatch):
    dummy_resp = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"caption_en": "desc"}')
            )
        ]
    )
    monkeypatch.setattr(
        caption.openai.chat.completions, "create", lambda *a, **k: dummy_resp
    )
    monkeypatch.setattr(caption, "MEDIA_DIR", tmp_path)

    img = tmp_path / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"data")

    caption.caption_file(img)
    out = img.with_suffix(".caption.json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["caption_en"].strip() == "desc"


def test_caption_logs(tmp_path, monkeypatch):
    log_path = Path(LOGFILE)
    log_path.write_text("")

    dummy_resp = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"caption_en": "desc"}')
            )
        ]
    )
    monkeypatch.setattr(
        caption.openai.chat.completions, "create", lambda *a, **k: dummy_resp
    )
    monkeypatch.setattr(caption, "MEDIA_DIR", tmp_path)

    img = tmp_path / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"data")

    caption.caption_file(img)

    data = log_path.read_text()
    assert "img.jpg" in data
    # Only warnings and errors are written to the file, so the caption text
    # does not appear when preprocessing succeeds. The error log includes the
    # filename which is enough to confirm logging works.

