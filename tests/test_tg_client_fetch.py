import importlib
import asyncio
import datetime
import types
import sys
from tg_client_test_utils import _install_telethon_stub, _DummyMessage, _DummyClient


def test_get_last_id(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    cfg.KEEP_DAYS = 7
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.import_module("tg_client")
    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)

    chat = "chat1"
    chat_dir = tmp_path / chat / "2024" / "05"
    chat_dir.mkdir(parents=True)
    (chat_dir / "1.md").write_text("msg1")
    (chat_dir / "3.md").write_text("msg3")

    assert tg_client.get_last_id(chat) == 3


# ---- fetch-missing tests -----------------------------------------------------

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
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")

    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(days=7)
    msgs = [
        _DummyMessage(1, start + datetime.timedelta(hours=1)),
        _DummyMessage(2, start + datetime.timedelta(hours=20)),
        _DummyMessage(3, start + datetime.timedelta(hours=25)),
    ]
    client = _DummyClient(msgs)

    saved = []

    async def save_stub(_c, _chat, msg, **_):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [1, 2, 3]


def test_fetch_missing_skips_old(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["chat"]
    cfg.KEEP_DAYS = 7
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")

    now = datetime.datetime.now(datetime.timezone.utc)
    old = now - datetime.timedelta(days=cfg.KEEP_DAYS + 1)
    client = _DummyClient([_DummyMessage(1, old)])

    saved = []

    async def save_stub(_c, _chat, msg, **_):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == []


def test_fetch_missing_naive_timestamp(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["chat"]
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(tg_client, "RAW_DIR", raw_dir)
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")

    msg_dir = raw_dir / "chat" / "2024" / "05"
    msg_dir.mkdir(parents=True)
    (msg_dir / "5.md").write_text("date: 2024-05-20T10:00:00\n\n")

    next_time = datetime.datetime(2024, 5, 20, 12, tzinfo=datetime.timezone.utc)
    client = _DummyClient([_DummyMessage(6, next_time)])

    saved = []

    async def save_stub(_c, _chat, msg, **_):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [6]


def test_fetch_missing_backfill(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["chat"]
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(tg_client, "RAW_DIR", raw_dir)

    now = datetime.datetime.now(datetime.timezone.utc)
    first = now - datetime.timedelta(days=5)

    msg_dir = raw_dir / "chat" / f"{first:%Y}" / f"{first:%m}"
    msg_dir.mkdir(parents=True)
    (msg_dir / "5.md").write_text(f"date: {first.isoformat()}\n\n")

    old_day = first - datetime.timedelta(days=1)
    msgs = [
        _DummyMessage(1, old_day + datetime.timedelta(hours=1)),
        _DummyMessage(2, old_day + datetime.timedelta(hours=20)),
        _DummyMessage(3, old_day + datetime.timedelta(hours=25)),
    ]
    client = _DummyClient(msgs)

    saved = []

    async def save_stub(_c, _chat, msg, **_):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [1, 2]


def test_fetch_missing_ignores_stale_progress(tmp_path, monkeypatch):
    _install_telethon_stub(monkeypatch)

    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["chat"]
    cfg.KEEP_DAYS = 7
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path / "raw")
    state_dir = tmp_path / "state"
    monkeypatch.setattr(tg_client, "STATE_DIR", state_dir)

    now = datetime.datetime.now(datetime.timezone.utc)
    stale = now - datetime.timedelta(days=cfg.KEEP_DAYS + 20)
    state_dir.mkdir(parents=True)
    (state_dir / "chat.txt").write_text(stale.isoformat())

    old_msg_time = now - datetime.timedelta(days=cfg.KEEP_DAYS + 15)
    client = _DummyClient([_DummyMessage(1, old_msg_time)])

    saved = []

    async def save_stub(_c, _chat, msg, **_):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == []


# ---- ensure-access tests -----------------------------------------------------

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
    asyncio.run(tg_client.ensure_chat_access(DummyClient()))

    assert calls == cfg.CHATS
