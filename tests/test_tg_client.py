from pathlib import Path
import sys
import types
import importlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _install_telethon_stub(monkeypatch):
    tl_custom = types.ModuleType("telethon.tl.custom")
    tl_custom.Message = object
    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = object
    telethon.events = types.SimpleNamespace(NewMessage=object, MessageEdited=object)
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.tl.custom", tl_custom)


def test_get_last_id(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)
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


class _DummyMessage:
    def __init__(self, mid, date):
        self.id = mid
        self.date = date
        self.message = ""
        self.media = None
        self.reply_to_msg_id = None
        self.sender_id = 1


class _DummyClient:
    def __init__(self, msgs):
        self._msgs = msgs

    def iter_messages(self, chat, min_id=None, reverse=True):
        async def gen():
            for m in self._msgs:
                if min_id and m.id <= min_id:
                    continue
                yield m
        return gen()

    async def get_permissions(self, chat, user_id):
        return types.SimpleNamespace(is_admin=False)


import asyncio
from datetime import datetime, timedelta


def test_fetch_missing_day_limit(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["chat"]
    monkeypatch.setitem(sys.modules, "config", cfg)
    tg_client = importlib.reload(importlib.import_module("tg_client"))

    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path / "raw")

    now = datetime.utcnow()
    start = now - timedelta(days=31)
    msgs = [
        _DummyMessage(1, start + timedelta(hours=1)),
        _DummyMessage(2, start + timedelta(hours=20)),
        _DummyMessage(3, start + timedelta(hours=25)),
    ]
    client = _DummyClient(msgs)

    saved = []

    async def save_stub(_c, _chat, msg):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)

    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [1, 2]
