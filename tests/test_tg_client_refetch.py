import importlib
import asyncio
import datetime
import json
import types
import sys
from tg_client_test_utils import _install_telethon_stub, DummyMessage, fake_get_permissions


def test_refetch_messages(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "BROKEN_META_FILE", tmp_path / "broken.json")

    (tmp_path / "broken.json").write_text(json.dumps([{"chat": "chat", "id": 1}]))

    called = {"fetched": [], "saved": []}

    class DummyClient:
        async def get_messages(self, chat, ids):
            called["fetched"].append((chat, ids))
            return types.SimpleNamespace(
                id=ids, date=datetime.datetime.now(datetime.timezone.utc), message=""
            )

    async def save_stub(c, chat, msg, **_):
        called["saved"].append((chat, msg.id))

    monkeypatch.setattr(tg_client, "_save_bounded", save_stub)

    asyncio.run(tg_client.refetch_messages(DummyClient()))

    assert ("chat", 1) in called["fetched"]
    assert ("chat", 1) in called["saved"]
    assert not (tmp_path / "broken.json").exists()


def test_refetch_cleanup_deleted(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(tg_client, "RAW_DIR", raw_dir)
    monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(tg_client, "LOTS_DIR", tmp_path / "lots")
    broken = tmp_path / "broken.json"
    monkeypatch.setattr(tg_client, "BROKEN_META_FILE", broken)

    msg_dir = raw_dir / "chat" / "2024" / "05"
    msg_dir.mkdir(parents=True)
    md = msg_dir / "1.md"
    md.write_text("id: 1\ndate: 2024-05-01T00:00:00+00:00\n\n")
    broken.write_text(json.dumps([{"chat": "chat", "id": 1}]))

    class DummyClient:
        async def get_messages(self, chat, ids):
            return None

    asyncio.run(tg_client.refetch_messages(DummyClient()))

    assert not md.exists()
    assert not broken.exists()
