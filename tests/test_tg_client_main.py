import importlib
import asyncio
import datetime
import types
import sys
from tg_client_test_utils import _install_telethon_stub


def test_main_sequential_updates(monkeypatch):
    """Ensure TelegramClient is created with sequential_updates=True."""
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    called = {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            called.update(kwargs)

        async def start(self):
            pass

        def on(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        async def run_until_disconnected(self):
            return

    telethon = sys.modules["telethon"]
    monkeypatch.setattr(telethon, "TelegramClient", DummyClient)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "ensure_chat_access", lambda c: asyncio.sleep(0))
    monkeypatch.setattr(tg_client, "fetch_missing", lambda c: asyncio.sleep(0))

    asyncio.run(tg_client.main([]))

    assert called.get("sequential_updates") is True


def test_main_fetch_single(monkeypatch):
    """Verify ``--fetch`` downloads the requested message and exits."""
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    fetched = {}

    class DummyClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self):
            pass

        async def get_messages(self, chat, ids):
            fetched["msg"] = (chat, ids)
            return types.SimpleNamespace(
                id=ids, date=datetime.datetime.now(datetime.timezone.utc), message="t"
            )

    telethon = sys.modules["telethon"]
    monkeypatch.setattr(telethon, "TelegramClient", DummyClient)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(
        tg_client,
        "_save_bounded",
        lambda c, chat, msg, **_: asyncio.sleep(0),
    )

    asyncio.run(tg_client.main(["--fetch", "chat", "5"]))

    assert fetched.get("msg") == ("chat", 5)
