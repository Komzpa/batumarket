from pathlib import Path
import sys
import types
import importlib
import asyncio
import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_get_last_id(tmp_path, monkeypatch):
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
        content = files[0].read_text()
        assert "files" in content

    asyncio.run(run())
