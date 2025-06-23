import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_import_does_not_install_excepthook(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    if "scan_ontology" in sys.modules:
        del sys.modules["scan_ontology"]
    importlib.import_module("scan_ontology")
    assert sys.excepthook is sys.__excepthook__

