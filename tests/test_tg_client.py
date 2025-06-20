from pathlib import Path
import sys
import types
import importlib
import asyncio
import datetime

# ── dummy Telethon shims ────────────────────────────────────────────────────────
dummy_telethon = types.ModuleType("telethon")
dummy_telethon.TelegramClient = object
dummy_telethon.events = types.SimpleNamespace(
    NewMessage=lambda *a, **k: object,
    MessageEdited=lambda *a, **k: object,
)

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

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ── helpers ─────────────────────────────────────────────────────────────────────
def _install_telethon_stub(monkeypatch):
    """Inject a minimal Telethon stub into sys.modules for unit-tests."""
    tl_custom = types.ModuleType("telethon.tl.custom")
    tl_custom.Message = object
    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = object
    telethon.events = types.SimpleNamespace(
        NewMessage=lambda *a, **k: object,
        MessageEdited=lambda *a, **k: object,
    )
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.tl.custom", tl_custom)


# ── tests ───────────────────────────────────────────────────────────────────────
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


# ---- fetch-missing tests ------------------------------------------------------
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

    def iter_messages(self, chat, min_id=None, max_id=None, reverse=True, offset_date=None):
        async def gen():
            msgs = sorted(self._msgs, key=lambda m: m.date)
            if not reverse:
                msgs = list(reversed(msgs))
            for m in msgs:
                if min_id is not None and m.id <= min_id:
                    continue
                if max_id is not None and m.id >= max_id:
                    continue
                if offset_date is not None and m.date <= offset_date:
                    continue
                yield m

        return gen()

    async def get_permissions(self, chat, user_id):
        return types.SimpleNamespace(is_admin=False)


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
    start = now - datetime.timedelta(days=31)
    msgs = [
        _DummyMessage(1, start + datetime.timedelta(hours=1)),
        _DummyMessage(2, start + datetime.timedelta(hours=20)),
        _DummyMessage(3, start + datetime.timedelta(hours=25)),
    ]
    client = _DummyClient(msgs)

    saved = []

    async def save_stub(_c, _chat, msg):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [1, 2]


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
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(tg_client, "STATE_DIR", tmp_path / "state")

    # create a previous message with a naive timestamp
    msg_dir = raw_dir / "chat" / "2024" / "05"
    msg_dir.mkdir(parents=True)
    (msg_dir / "5.md").write_text("date: 2024-05-20T10:00:00\n\n")

    # place the next message within the one-day fetch window
    next_time = datetime.datetime(2024, 5, 20, 12, tzinfo=datetime.timezone.utc)
    client = _DummyClient([_DummyMessage(6, next_time)])

    saved = []

    async def save_stub(_c, _chat, msg):
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

    # existing message five days old
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

    async def save_stub(_c, _chat, msg):
        saved.append(msg.id)

    monkeypatch.setattr(tg_client, "_save_message", save_stub)
    asyncio.run(tg_client.fetch_missing(client))

    assert saved == [1, 2]


# ---- ensure-access tests ------------------------------------------------------
def test_ensure_chat_access(monkeypatch):
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = ["a", "b"]
    monkeypatch.setitem(sys.modules, "config", cfg)

    # Reload to pick up new config
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


# ---- grouped-message tests ----------------------------------------------------
class DummyMessage:
    def __init__(self, msg_id, date, grouped_id=None, text="", media=False):
        self.id = msg_id
        self.date = date
        self.grouped_id = grouped_id
        self.message = text
        self.media = media
        self.sender_id = 1
        self.reply_to_msg_id = None
        if media:
            self.file = types.SimpleNamespace(ext=".jpg", name="img.jpg")
        else:
            self.file = None

    async def download_media(self, *_, **__):
        return b"data"

    async def get_sender(self):
        return types.SimpleNamespace(
            first_name="John",
            last_name="Doe",
            username="john",
            phone="123",
        )


def fake_get_permissions(chat, user):
    return types.SimpleNamespace(is_admin=False)


def test_grouped_message(tmp_path, monkeypatch):
    async def run():
        cfg = types.ModuleType("config")
        cfg.TG_API_ID = 0
        cfg.TG_API_HASH = ""
        cfg.TG_SESSION = ""
        cfg.CHATS = []
        monkeypatch.setitem(sys.modules, "config", cfg)

        tg_client = importlib.import_module("tg_client")

        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)

        date = datetime.datetime(2024, 5, 1)
        msg1 = DummyMessage(1, date, grouped_id=10, text="hello", media=True)
        msg2 = DummyMessage(2, date, grouped_id=10, media=True)

        await tg_client._save_message(client, "chat", msg1)
        await tg_client._save_message(client, "chat", msg2)

        chat_dir = tmp_path / "chat" / "2024" / "05"
        files = list(chat_dir.glob("*.md"))
        assert len(files) == 1
        assert "files" in files[0].read_text()

    asyncio.run(run())


def test_save_message_skip_missing_media(tmp_path, monkeypatch):
    async def run():
        cfg = types.ModuleType("config")
        cfg.TG_API_ID = 0
        cfg.TG_API_HASH = ""
        cfg.TG_SESSION = ""
        cfg.CHATS = []
        monkeypatch.setitem(sys.modules, "config", cfg)

        tg_client = importlib.import_module("tg_client")

        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

        class NoData(DummyMessage):
            async def download_media(self, *_, **__):
                return None

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)

        date = datetime.datetime(2024, 5, 1)
        msg = NoData(1, date, media=True)

        await tg_client._save_message(client, "chat", msg)

        md_file = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert md_file.exists()
        text = md_file.read_text()
        assert "files" not in text

    asyncio.run(run())


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

    asyncio.run(tg_client.main())

    assert called.get("sequential_updates") is True
