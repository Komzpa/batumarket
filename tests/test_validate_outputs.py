from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import validate_outputs


def test_check_captions(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_outputs, "MEDIA_DIR", tmp_path / "media")
    d = validate_outputs.MEDIA_DIR
    d.mkdir(parents=True)
    (d / "img.jpg").write_bytes(b"x")
    (d / "img.caption.md").write_text("cap")
    assert validate_outputs.check_captions()


def test_check_captions_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_outputs, "MEDIA_DIR", tmp_path / "media")
    d = validate_outputs.MEDIA_DIR
    d.mkdir(parents=True)
    (d / "img.jpg").write_bytes(b"x")
    assert not validate_outputs.check_captions()
