from pathlib import Path
import sys
import types
import os

# Provide stubs before importing the module
dummy_openai = types.ModuleType("openai")
dummy_openai.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda *a, **k: None))
sys.modules["openai"] = dummy_openai

dummy_cfg = types.ModuleType("config")
dummy_cfg.OPENAI_KEY = ""
dummy_cfg.LANGS = ["en"]
sys.modules["config"] = dummy_cfg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import chop


def test_chop_processes_nested(tmp_path, monkeypatch):
    dummy_resp = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="[]"))]
    )
    called = {}
    def fake_create(*a, **k):
        called.update(k)
        return dummy_resp
    monkeypatch.setattr(chop.openai.chat.completions, "create", fake_create)
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    msg = tmp_path / "raw" / "chat" / "2024" / "05" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1\n\nhello", encoding="utf-8")

    chop.main()

    assert (tmp_path / "lots" / "chat" / "2024" / "05" / "1.json").exists()
    assert called.get("response_format") == {"type": "json_object"}


def test_build_prompt():
    msg = "hello"
    files = ["a.jpg", "b.jpg"]
    caps = ["cap a", "cap b"]
    prompt = chop._build_prompt(msg, files, caps)
    assert "Message text:" in prompt
    assert "Image a.jpg" in prompt
    assert "cap a" in prompt


def test_main_sorts_by_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    newer = tmp_path / "raw" / "chat" / "2024" / "05" / "2.md"
    older = tmp_path / "raw" / "chat" / "2024" / "05" / "1.md"
    for p in (newer, older):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("id: x", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    processed = []
    monkeypatch.setattr(chop, "process_message", lambda p: processed.append(p))

    chop.main()
    assert processed == [newer, older]
