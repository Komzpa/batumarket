import asyncio
import importlib
import types
import sys
from tg_client_test_utils import _install_telethon_stub


def test_flush_chop_queue_timeout(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
    monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(tg_client, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(tg_client, "CHOP_FLUSH_TIMEOUT", 0)
    monkeypatch.setattr(tg_client, "CHOP_CHECK_INTERVAL", 0)

    path = tmp_path / "chat" / "2024" / "05" / "1.md"
    tg_client._CHOP_QUEUE[path] = {"timestamp": 0.0, "pending": {tmp_path / "img.jpg"}}

    async def run():
        tg_client._chop_task = asyncio.create_task(asyncio.sleep(0))
        await tg_client._flush_chop_queue()
        assert tg_client._chop_task is None
        assert path in tg_client._CHOP_QUEUE

    asyncio.run(run())
