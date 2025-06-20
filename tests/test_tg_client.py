from pathlib import Path
import sys
import types
import importlib

dummy_telethon = types.ModuleType("telethon")
dummy_telethon.TelegramClient = object
dummy_telethon.events = types.SimpleNamespace()
dummy_custom = types.ModuleType("telethon.tl.custom")
dummy_custom.Message = object
dummy_funcs = types.ModuleType("telethon.tl.functions.channels")
dummy_funcs.JoinChannelRequest = lambda chat: types.SimpleNamespace(chat=chat)
dummy_errors = types.ModuleType("telethon.errors")
class DummyError(Exception):
    pass
dummy_errors.UserAlreadyParticipantError = DummyError
sys.modules["telethon"] = dummy_telethon
sys.modules["telethon.tl.custom"] = dummy_custom
sys.modules["telethon.tl.functions.channels"] = dummy_funcs
sys.modules["telethon.errors"] = dummy_errors

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
    chat_dir = tmp_path / chat / "2024" / "05"
    chat_dir.mkdir(parents=True)
    (chat_dir / "1.md").write_text("msg1")
    (chat_dir / "3.md").write_text("msg3")
    assert tg_client.get_last_id(chat) == 3


def test_ensure_chat_access(monkeypatch):
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["a", "b"]
    monkeypatch.setitem(sys.modules, "config", cfg)
    sys.modules.pop("tg_client", None)
    tg_client = importlib.import_module("tg_client")

    calls = []

    class DummyClient:
        async def __call__(self, req):
            calls.append(req.chat)

    class DummyReq:
        def __init__(self, chat):
            self.chat = chat

    monkeypatch.setattr(tg_client, "JoinChannelRequest", DummyReq)

    import asyncio
    asyncio.run(tg_client.ensure_chat_access(DummyClient()))
    assert calls == cfg.CHATS
