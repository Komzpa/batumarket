"""Utilities to make scripts behave consistently under tests."""

import os
from log_utils import get_logger

log = get_logger().bind(script=__name__)


def apply_testing_mode():
    """Tweak environment variables when ``TEST_MODE`` is set."""
    if os.getenv("TEST_MODE") == "1":
        log.info("Testing mode active")
        os.environ.setdefault("OPENAI_KEY", "test")
