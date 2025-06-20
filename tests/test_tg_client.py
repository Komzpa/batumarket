from pathlib import Path
import sys
import types
import importlib
import asyncio
import datetime

# ── dummy Telethon shims ────────────────────────────────────────────────────────
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

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ── helpers ─────────────────────────────────────────────────────────────────────
def _install_telethon_stub(monkeypatch):
    """Inject a minimal Telethon stub into sys.modules for unit-tests."""
    tl_custom = types.ModuleType("telethon.tl.custom")
    tl_custom.Message = object
    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = object
    telethon.events = types.SimpleNamespace(NewMessage=object, MessageEdited=object)
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

    def iter_messages(self, chat, min_id=None, reverse=True):
        async def gen():
            for m in self._msgs:
                if min_id and m.id <= min_id:
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

    now = datetime.datetime.utcnow()
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

    async def download_media(self, *_):
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
