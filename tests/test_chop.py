from pathlib import Path
import sys
import types
import os
import json

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
    monkeypatch.setattr(chop.embed, "embed_file", lambda p: None)

    msg = tmp_path / "raw" / "chat" / "2024" / "05" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1\n\nhello", encoding="utf-8")

    chop.main([str(msg)])

    assert (tmp_path / "lots" / "chat" / "2024" / "05" / "1.json").exists()
    fmt = called.get("response_format", {}).get("json_schema", {})
    assert called.get("response_format", {}).get("type") == "json_schema"
    assert fmt.get("name") == "extract_lots"
    assert called["timeout"] == chop.OPENAI_TIMEOUT


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


def test_chop_reruns_for_multiple_lots(tmp_path, monkeypatch):
    """When gpt-4o-mini returns multiple lots the post is reprocessed."""
    resp_mini = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=json.dumps(
                        {
                            "lots": [
                                {
                                    "title_en": "a",
                                    "description_en": "d",
                                    "title_ru": "a",
                                    "description_ru": "d",
                                    "title_ka": "a",
                                    "description_ka": "d",
                                    "files": []
                                },
                                {
                                    "title_en": "b",
                                    "description_en": "d",
                                    "title_ru": "b",
                                    "description_ru": "d",
                                    "title_ka": "b",
                                    "description_ka": "d",
                                    "files": []
                                },
                            ]
                        }
                    )
                )
            )
        ]
    )
    resp_full = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=json.dumps([
                        {
                            "title_en": "ok",
                            "description_en": "d",
                            "title_ru": "ok",
                            "description_ru": "d",
                            "title_ka": "ok",
                            "description_ka": "d"
                        }
                    ])
                )
            )
        ]
    )
    responses = [resp_mini, resp_full]
    called = []

    def fake_create(*a, **k):
        called.append(k.get("model"))
        return responses.pop(0)

    monkeypatch.setattr(chop.openai.chat.completions, "create", fake_create)
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    msg = tmp_path / "raw" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1", encoding="utf-8")

    chop.main([str(msg)])

    assert called == ["gpt-4o-mini", "gpt-4o"]
    out = tmp_path / "lots" / "1.json"
    assert out.exists()


def test_chop_reruns_when_lot_needs_cleanup(tmp_path, monkeypatch):
    """Mini model output lacking translations triggers the full model."""
    resp_mini = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=json.dumps([
                        {
                            "title_en": "only",
                            "description_en": "d"
                        }
                    ])
                )
            )
        ]
    )
    resp_full = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=json.dumps([
                        {
                            "title_en": "ok",
                            "description_en": "d",
                            "title_ru": "ok",
                            "description_ru": "d",
                            "title_ka": "ok",
                            "description_ka": "d"
                        }
                    ])
                )
            )
        ]
    )
    responses = [resp_mini, resp_full]
    called = []

    def fake_create(*a, **k):
        called.append(k.get("model"))
        return responses.pop(0)

    monkeypatch.setattr(chop.openai.chat.completions, "create", fake_create)
    monkeypatch.setattr(chop, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(chop, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(chop, "MEDIA_DIR", tmp_path / "media")

    msg = tmp_path / "raw" / "1.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("id: 1", encoding="utf-8")

    chop.main([str(msg)])

    assert called == ["gpt-4o-mini", "gpt-4o"]
    assert (tmp_path / "lots" / "1.json").exists()


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

