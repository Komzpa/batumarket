from pathlib import Path
import sys
import types
import importlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_get_last_id(tmp_path, monkeypatch):
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)
    tg_client = importlib.import_module("tg_client")

    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
    chat = "chat1"
    chat_dir = tmp_path / chat
    chat_dir.mkdir()
    (chat_dir / "1.md").write_text("msg1")
    (chat_dir / "3.md").write_text("msg3")
    assert tg_client.get_last_id(chat) == 3
