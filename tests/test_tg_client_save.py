import importlib
import asyncio
import datetime
import hashlib
import types
import sys
from tg_client_test_utils import DummyMessage, fake_get_permissions


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
    assert tg_client._should_skip_media(msg) is None


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
                self.file = types.SimpleNamespace(ext=".mp4", mime_type="video/mp4", size=100)

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
                self.file = types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", size=100)

            async def download_media(self, *_, **__):
                called["d"] = True
                return b"data"

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)
        old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
        msg = Old(1, old_date)

        await tg_client._save_message(client, "chat", msg)

        assert called["d"] is True
        md_file = tmp_path / "chat" / f"{old_date:%Y}" / f"{old_date:%m}" / "1.md"
        assert md_file.exists()
        text = md_file.read_text()
        assert "files" in text
        assert "skipped_media" not in text

    asyncio.run(run())


def test_save_message_force_media(tmp_path, monkeypatch):
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
                self.file = types.SimpleNamespace(ext=".jpg", mime_type="image/jpeg", size=100)

            async def download_media(self, *_, **__):
                called["d"] = True
                return b"data"

        client = types.SimpleNamespace(get_permissions=fake_get_permissions)
        old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
        msg = Old(1, old_date)

        await tg_client._save_message(client, "chat", msg, force_media=True)

        assert called["d"] is True
        md_file = tmp_path / "chat" / f"{old_date:%Y}" / f"{old_date:%m}" / "1.md"
        assert md_file.exists()
        text = md_file.read_text()
        assert "files" in text
        assert "skipped_media" not in text

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

        old_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)

        subdir = tmp_path / "chat" / f"{old_date:%Y}" / f"{old_date:%m}"
        subdir.mkdir(parents=True)
        media_subdir = tmp_path / "media" / "chat" / f"{old_date:%Y}" / f"{old_date:%m}"
        media_subdir.mkdir(parents=True)
        (media_subdir / "img.jpg").write_bytes(b"data")

        existing = subdir / "1.md"
        existing.write_text(
            f"id: 1\nchat: chat\ndate: {old_date.isoformat()}\nsender_username:u\nfiles: ['chat/{old_date:%Y}/{old_date:%m}/img.jpg']\n\nold"
        )

        class Old(DummyMessage):
            def __init__(self, mid, date):
                super().__init__(mid, date, media=True)
                self.file = types.SimpleNamespace(
                    ext=".jpg",
                    mime_type="image/jpeg",
                    size=100,
                    name="img.jpg",
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
