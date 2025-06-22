from pathlib import Path
import sys
import types
import os
import datetime

os.environ.setdefault("TEST_MODE", "1")

# --- dummy Telethon shims ----------------------------------------------------

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


# --- helpers -----------------------------------------------------------------

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


# --- fetch-missing helpers ---------------------------------------------------

class _DummyMessage:
    def __init__(self, mid: int, date: datetime.datetime):
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


# --- grouped-message helpers -------------------------------------------------

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

