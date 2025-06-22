from pathlib import Path
import sys
import types
import os
import importlib
import asyncio
import datetime
import hashlib
import json

# Ensure helper functions skip external API calls during tests
os.environ.setdefault("TEST_MODE", "1")

# ── dummy Telethon shims ────────────────────────────────────────────────────────
dummy_telethon = types.ModuleType("telethon")
dummy_telethon.TelegramClient = object
dummy_telethon.events = types.SimpleNamespace(
    NewMessage=lambda *a, **k: object,
    Album=lambda *a, **k: object,
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

# Minimal progressbar stub
dummy_progressbar = types.ModuleType("progressbar")


class _DummyPB:
    def __init__(self, *a, **k):
        pass

    def start(self):
        return self

    def update(self, *_):
        return self

    def finish(self):
        return self


dummy_progressbar.Bar = lambda *a, **k: None
dummy_progressbar.ETA = lambda *a, **k: None
dummy_progressbar.ProgressBar = lambda *a, **k: _DummyPB()
sys.modules["progressbar"] = dummy_progressbar

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
        Album=lambda *a, **k: object,
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

    def iter_messages(
        self, chat, min_id=None, max_id=None, reverse=True, offset_date=None
    ):
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

        tg_client = importlib.reload(importlib.import_module("tg_client"))

        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")
        monkeypatch.setattr(tg_client, "_schedule_chop", lambda p: None)

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


def test_grouped_message_resume(tmp_path, monkeypatch):
    async def run():
        cfg = types.ModuleType("config")
        cfg.TG_API_ID = 0
        cfg.TG_API_HASH = ""
        cfg.TG_SESSION = ""
        cfg.CHATS = []
        monkeypatch.setitem(sys.modules, "config", cfg)

        tg_client = importlib.reload(importlib.import_module("tg_client"))

        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)

        date = datetime.datetime(2024, 5, 1)
        msg1 = DummyMessage(1, date, grouped_id=11, media=True)
        msg2 = DummyMessage(2, date, grouped_id=11, text="caption", media=True)

        await tg_client._save_message(client, "chat", msg1)
        tg_client._GROUPS.clear()
        await tg_client._save_message(client, "chat", msg2)

        chat_dir = tmp_path / "chat" / "2024" / "05"
        files = list(chat_dir.glob("*.md"))
        assert len(files) == 1
        text = files[0].read_text()
        assert "id: 2" in text

    asyncio.run(run())


def test_remove_deleted_recent(tmp_path, monkeypatch):
    async def run():
        cfg = types.ModuleType("config")
        cfg.TG_API_ID = 0
        cfg.TG_API_HASH = ""
        cfg.TG_SESSION = ""
        cfg.CHATS = ["chat"]
        cfg.KEEP_DAYS = 7
        monkeypatch.setitem(sys.modules, "config", cfg)

        tg_client = importlib.reload(importlib.import_module("tg_client"))

        now = datetime.datetime.now(datetime.timezone.utc)
        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

        msg_dir = tmp_path / "chat" / f"{now:%Y}" / f"{now:%m}"
        msg_dir.mkdir(parents=True)
        md = msg_dir / "1.md"
        md.write_text(f"id: 1\ndate: {now.isoformat()}\n\n")

        class DummyClient:
            async def get_messages(self, chat, ids):
                return None

        await tg_client.remove_deleted(DummyClient(), cfg.KEEP_DAYS)

        assert not md.exists()

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
        monkeypatch.setattr(tg_client, "_schedule_chop", lambda p: None)

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
        assert "skipped_media" in text

    asyncio.run(run())


def test_should_skip_media(monkeypatch):
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.import_module("tg_client")

    file1 = types.SimpleNamespace(ext=".mp4", mime_type="video/mp4", size=100)
    assert tg_client._should_skip_media(types.SimpleNamespace(file=file1)) == "video"

    file2 = types.SimpleNamespace(ext=".mp3", mime_type="audio/mpeg", size=100)
    assert tg_client._should_skip_media(types.SimpleNamespace(file=file2)) == "audio"

    big = 11 * 1024 * 1024
    file3 = types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", size=big)
    assert (
        tg_client._should_skip_media(types.SimpleNamespace(file=file3))
        == "image-too-large"
    )

    file4 = types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", size=1024)
    assert tg_client._should_skip_media(types.SimpleNamespace(file=file4)) is None

    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
    file5 = types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", size=100)
    msg = types.SimpleNamespace(date=old, file=file5)
    assert tg_client._should_skip_media(msg) == "old"


def test_save_message_respects_skip(tmp_path, monkeypatch):
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

        called = {"d": False}

        class Skip(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date, media=True)
                self.file = types.SimpleNamespace(
                    ext=".mp4", mime_type="video/mp4", size=100
                )

            async def download_media(self, *_, **__):
                called["d"] = True
                return b"data"

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)
        date = datetime.datetime(2024, 5, 1)
        msg = Skip(1, date)

        await tg_client._save_message(client, "chat", msg)

        assert called["d"] is False
        md_file = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert md_file.exists()
        text = md_file.read_text()
        assert "files" not in text
        assert "skipped_media" in text

    asyncio.run(run())


def test_save_message_skip_old_media(tmp_path, monkeypatch):
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

        called = {"d": False}

        class Old(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date, media=True)
                self.file = types.SimpleNamespace(
                    ext=".jpg", mime_type="image/jpeg", size=100
                )

            async def download_media(self, *_, **__):
                called["d"] = True
                return b"data"

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)
        old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=3
        )
        msg = Old(1, old_date)

        await tg_client._save_message(client, "chat", msg)

        assert called["d"] is False
        md_file = tmp_path / "chat" / f"{old_date:%Y}" / f"{old_date:%m}" / "1.md"
        assert md_file.exists()
        text = md_file.read_text()
        assert "files" not in text
        assert "skipped_media" in text

    asyncio.run(run())


def test_save_message_keep_existing_media(tmp_path, monkeypatch):
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
        monkeypatch.setattr(tg_client, "_schedule_chop", lambda p: None)

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)

        old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=3
        )

        subdir = tmp_path / "chat" / f"{old_date:%Y}" / f"{old_date:%m}"
        subdir.mkdir(parents=True)
        media_subdir = tmp_path / "media" / "chat" / f"{old_date:%Y}" / f"{old_date:%m}"
        media_subdir.mkdir(parents=True)
        (media_subdir / "img.jpg").write_bytes(b"data")

        existing = subdir / "1.md"
        existing.write_text(
            f"id: 1\nchat: chat\ndate: {old_date.isoformat()}\nsender_username: u\nfiles: ['chat/{old_date:%Y}/{old_date:%m}/img.jpg']\n\nold"
        )

        class Old(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date, media=True)
                self.file = types.SimpleNamespace(
                    ext=".jpg", mime_type="image/jpeg", size=100, name="img.jpg"
                )

            async def download_media(self, *_, **__):
                raise AssertionError("no download")

        msg = Old(1, old_date)

        await tg_client._save_message(client, "chat", msg)

        text = existing.read_text()
        assert "skipped_media" not in text

    asyncio.run(run())


def test_save_message_text_attr(tmp_path, monkeypatch):
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

        class Txt(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date)
                self.message = ""
                self.text = "caption text"

        msg = Txt(1, date)

        await tg_client._save_message(client, "chat", msg)

        md_file = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert md_file.exists()
        assert "caption text" in md_file.read_text()

    asyncio.run(run())


def test_save_message_missing_sender(tmp_path, monkeypatch):
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

        class NoSender(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date)
                self.sender_id = None

            async def get_sender(self):
                return types.SimpleNamespace(first_name="Ann")

        msg = NoSender(1, date)

        await tg_client._save_message(client, "chat", msg)

        md_file = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert md_file.exists()

    asyncio.run(run())


def test_save_message_topic_filter(tmp_path, monkeypatch):
    async def run():
        cfg = types.ModuleType("config")
        cfg.TG_API_ID = 0
        cfg.TG_API_HASH = ""
        cfg.TG_SESSION = ""
        cfg.CHATS = ["chat/101"]
        monkeypatch.setitem(sys.modules, "config", cfg)

        tg_client = importlib.import_module("tg_client")

        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)

        date = datetime.datetime(2024, 5, 1)
        header = types.SimpleNamespace(
            reply_to_msg_id=101,
            reply_to_top_id=101,
            forum_topic=True,
        )

        class Topic(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date)
                self.reply_to = header

        msg = Topic(1, date)

        await tg_client._save_message(client, "chat", msg)

        md_file = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert md_file.exists()

        cfg.CHATS = ["chat/999"]
        tg_client = importlib.reload(importlib.import_module("tg_client"))
        monkeypatch.setattr(tg_client, "RAW_DIR", tmp_path)
        monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")
        monkeypatch.setattr(tg_client, "_schedule_chop", lambda p: None)

        msg2 = Topic(2, date)
        await tg_client._save_message(client, "chat", msg2)

        md_file2 = tmp_path / "chat" / "2024" / "05" / "2.md"
        assert not md_file2.exists()

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

    called = {"fetched": [], "saved": []}

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


def test_save_media_reschedules_caption(tmp_path, monkeypatch):
    cfg = types.ModuleType("config")
    cfg.TG_API_ID = 0
    cfg.TG_API_HASH = ""
    cfg.TG_SESSION = ""
    cfg.CHATS = []
    monkeypatch.setitem(sys.modules, "config", cfg)

    tg_client = importlib.reload(importlib.import_module("tg_client"))
    monkeypatch.setattr(tg_client, "MEDIA_DIR", tmp_path / "media")

    data = b"img"
    sha = hashlib.sha256(data).hexdigest()
    date = datetime.datetime(2024, 5, 1, tzinfo=datetime.timezone.utc)
    subdir = tg_client.MEDIA_DIR / "chat" / f"{date:%Y}" / f"{date:%m}"
    subdir.mkdir(parents=True)
    existing = subdir / f"{sha}.jpg"
    existing.write_bytes(data)

    called = {"c": False}

    def cap(path):
        called["c"] = True

    monkeypatch.setattr(tg_client, "_schedule_caption", cap)

    msg = types.SimpleNamespace(
        id=1,
        date=date,
        file=types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", name="img.jpg"),
    )

    asyncio.run(tg_client._save_media("chat", msg, data))

    assert called["c"] is True


def test_save_message_schedules_chop(tmp_path, monkeypatch):
    async def run():
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

        called = {}

        def sched(path):
            called["path"] = path

        monkeypatch.setattr(tg_client, "_schedule_chop", sched)
        monkeypatch.setattr(tg_client, "CHOP_COOLDOWN", 0)

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)
        date = datetime.datetime(2024, 5, 1, tzinfo=datetime.timezone.utc)
        msg = DummyMessage(1, date, text="hi")

        await tg_client._save_message(client, "chat", msg)
        tg_client._process_chop_queue()

        expected = tmp_path / "chat" / "2024" / "05" / "1.md"
        assert called.get("path") == expected

    asyncio.run(run())


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
