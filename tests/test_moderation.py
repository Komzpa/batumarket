from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import moderation


def test_should_skip_text():
    spam = "Прошу подпишитесь на канал @flats_in_georgia чтобы я пропускал ваши сообщения в этот чат!"
    assert moderation.should_skip_text(spam)
    assert not moderation.should_skip_text("normal text")


def test_should_skip_lot():
    lot = {"contact:telegram": "@username"}
    assert moderation.should_skip_lot(lot)
    assert not moderation.should_skip_lot({"contact:telegram": "@real", "title_en": "x", "description_en": "d", "title_ru": "x", "description_ru": "d", "title_ka": "x", "description_ka": "d"})
    incomplete = {"contact:telegram": "@real", "title_en": "x"}
    assert moderation.should_skip_lot(incomplete)


def test_should_skip_fraud():
    lot = {
        "fraud": "drugs",
        "contact:telegram": "@real",
        "title_en": "x",
        "description_en": "d",
        "title_ru": "x",
        "description_ru": "d",
        "title_ka": "x",
        "description_ka": "d",
    }
    assert moderation.should_skip_lot(lot)
