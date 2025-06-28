import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_import_does_not_install_excepthook(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    if "cluster_items" in sys.modules:
        del sys.modules["cluster_items"]
    importlib.import_module("cluster_items")
    assert sys.excepthook is sys.__excepthook__

