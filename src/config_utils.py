"""Utility to load the user configuration."""

from importlib import import_module
from pathlib import Path
import sys

from log_utils import get_logger

log = get_logger().bind(module=__name__)


def load_config():
    """Return the ``config`` module or exit with a helpful message.

    When running the scripts directly from ``src/`` the repository root isn't on
    ``sys.path`` and ``config.py`` can't be imported.  Try adding the parent
    directory before failing so the configuration can live alongside
    ``config.example.py`` in the project root.
    """

    try:
        return import_module("config")
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
            log.debug("Added repo root to sys.path", path=str(repo_root))
        try:
            return import_module("config")
        except ModuleNotFoundError as exc:
            log.error(
                "Missing config.py, copy config.example.py and fill in credentials"
            )
            raise SystemExit("Configuration file 'config.py' not found") from exc

