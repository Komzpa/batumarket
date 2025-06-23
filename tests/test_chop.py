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
from message_utils import build_prompt


def test_chop_processes_nested(tmp_path, monkeypatch):
    dummy_resp = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"lots": []}')
            )
        ]
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

    chop.main([str(msg)])

    assert (tmp_path / "lots" / "chat" / "2024" / "05" / "1.json").exists()
    fmt = called.get("response_format", {}).get("json_schema", {})
    assert called.get("response_format", {}).get("type") == "json_schema"
    assert fmt.get("name") == "extract_lots"


def test_chop_triggers_embed(tmp_path, monkeypatch):
    dummy_resp = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"lots": []}')
            )
        ]
    )
    monkeypatch.setattr(chop.openai.chat.completions, "create", lambda *a, **k: dummy_resp)
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")
    called = []
    monkeypatch.setattr(chop.embed, "embed_file", lambda p: called.append(p))

    msg = tmp_path / "raw" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1", encoding="utf-8")

    chop.main([str(msg)])

    assert called == [tmp_path / "lots" / "1.json"]


def test_build_prompt():
    msg = "hello"
    files = ["a.jpg", "b.jpg"]
    caps = ["cap a", "cap b"]
    prompt = build_prompt(msg, files, caps)
    assert "Message text:" in prompt
    assert "Image a.jpg" in prompt
    assert "cap a" in prompt


def test_main_cli_argument(tmp_path, monkeypatch):
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    msg = tmp_path / "raw" / "chat" / "2024" / "05" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: x", encoding="utf-8")

    processed = []
    monkeypatch.setattr(chop, "process_message", lambda p: processed.append(p))

    chop.main([str(msg)])
    assert processed == [msg]


def test_chop_skips_moderated(tmp_path, monkeypatch):
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    msg = tmp_path / "raw" / "chat" / "2024" / "05" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1\n\nspam", encoding="utf-8")

    monkeypatch.setattr(chop, "should_skip_message", lambda m, t: True)

    chop.main([str(msg)])

    assert not (tmp_path / "lots" / "chat" / "2024" / "05" / "1.json").exists()

