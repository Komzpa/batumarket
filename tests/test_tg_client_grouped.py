import importlib
import asyncio
import datetime
import types
import sys
from tg_client_test_utils import _install_telethon_stub, DummyMessage, fake_get_permissions


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
