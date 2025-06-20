from pathlib import Path
import sys
import types

# Provide a minimal ``openai`` stub before importing the module under test.
dummy_openai = types.ModuleType("openai")
dummy_openai.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda *a, **k: None))
sys.modules["openai"] = dummy_openai

# Minimal config stub required by ``caption`` module.
dummy_cfg = types.ModuleType("config")
dummy_cfg.OPENAI_KEY = ""
sys.modules["config"] = dummy_cfg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import caption


def test_caption_file_writes(tmp_path, monkeypatch):
    dummy_resp = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="desc"))]
    )
    monkeypatch.setattr(
        caption.openai.chat.completions, "create", lambda *a, **k: dummy_resp
    )
    monkeypatch.setattr(caption, "MEDIA_DIR", tmp_path)

    img = tmp_path / "chat" / "2024" / "05" / "img.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"data")

    caption.caption_file(img)
    out = img.with_suffix(".caption.md")
    assert out.exists()
    assert out.read_text().strip() == "desc"
