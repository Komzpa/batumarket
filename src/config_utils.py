"""Utility to load the user configuration."""

from importlib import import_module

from log_utils import get_logger

log = get_logger().bind(module=__name__)


def load_config():
    """Return the ``config`` module or exit with a helpful message."""
    try:
        return import_module("config")
    except ModuleNotFoundError as exc:
        log.error(
            "Missing config.py, copy config.example.py and fill in credentials"
        )
        raise SystemExit("Configuration file 'config.py' not found") from exc

