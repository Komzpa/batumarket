import sys
import types
from pathlib import Path
import importlib

# stub config
dummy_cfg = types.ModuleType("config")
dummy_cfg.TG_TOKEN = "123"
dummy_cfg.LANGS = ["en", "ru"]
sys.modules["config"] = dummy_cfg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    telegram_bot = importlib.reload(importlib.import_module("telegram_bot"))
except Exception as e:  # pragma: no cover - optional dependency
    import pytest
    pytest.skip(f"telegram bot deps missing: {e}", allow_module_level=True)



def test_enqueue(tmp_path):
    telegram_bot.PROFILES_PATH = tmp_path / "profiles.json"
    import similar_utils
    similar_utils.EMBED_DIR = tmp_path / "emb"
    telegram_bot.LOTS_DIR = tmp_path / "lots"
    telegram_bot.PROFILES_PATH.write_text("{}")
    telegram_bot.embeddings = {"foo": [1, 0]}
    telegram_bot.profiles = {"1": {"lang": "en", "likes": [], "dislikes": [], "queue": []}}
    telegram_bot.enqueue_new_ids(["foo"])
    assert telegram_bot.profiles["1"]["queue"] == ["foo"]


def test_start_cmd(tmp_path):
    telegram_bot.PROFILES_PATH = tmp_path / "profiles.json"
    telegram_bot.profiles = {}

    class DummyMsg:
        def __init__(self):
            self.text = None

        async def reply_text(self, text):
            self.text = text

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=2), message=DummyMsg()
    )
    context = types.SimpleNamespace(args=[])

    import asyncio

    asyncio.run(telegram_bot.start_cmd(update, context))
    assert "2" in telegram_bot.profiles
    assert update.message.text == "Registered"


def test_auto_register_lang(tmp_path):
    telegram_bot.PROFILES_PATH = tmp_path / "profiles.json"
    telegram_bot.profiles = {}

    class DummyMsg:
        def __init__(self):
            self.text = None

        async def reply_text(self, text):
            self.text = text

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=3), message=DummyMsg()
    )
    context = types.SimpleNamespace(args=["ru"])

    import asyncio

    asyncio.run(telegram_bot.lang_cmd(update, context))
    assert "3" in telegram_bot.profiles
    assert telegram_bot.profiles["3"]["lang"] == "ru"


def test_send_alert(monkeypatch):
    telegram_bot.profiles = {"1": {}, "2": {}}
    sent: list[tuple[int, str]] = []

    class DummyBot:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))

    class DummyBuilder:
        def token(self, _):
            return self

        def build(self):
            return types.SimpleNamespace(bot=DummyBot())

    monkeypatch.setattr(telegram_bot, "ApplicationBuilder", DummyBuilder)
    monkeypatch.setattr(telegram_bot, "load_profiles", lambda: None)

    import asyncio

    asyncio.run(telegram_bot.send_alert("hi"))
    assert sorted(sent) == [(1, "hi"), (2, "hi")]


def test_localization():
    assert telegram_bot._t("ru", "Registered") == "Вы зарегистрированы"


