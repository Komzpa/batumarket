import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import debug_dump


def test_parse_url():
    lot, lang = debug_dump.parse_url(
        "http://example.com/chat/2025/06/1234-0_ru.html"
    )
    assert lot == "chat/2025/06/1234-0"
    assert lang == "ru"


def test_guess_source_from_lot():
    chat, mid = debug_dump.guess_source_from_lot("chat/2025/06/1234-0")
    assert chat == "chat"
    assert mid == 1234


def test_run_tg_fetch_includes_stderr(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_MODE", raising=False)

    class DummyProc:
        stdout = "out"
        stderr = "err"

    def dummy_run(*_a, **_k):
        return DummyProc()

    monkeypatch.setattr(debug_dump.subprocess, "run", dummy_run)
    monkeypatch.chdir(tmp_path)
    out = debug_dump.run_tg_fetch("chat", 1)
    assert "out" in out
    assert "err" in out

