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

