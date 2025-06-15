"""Utility functions related to token counting.

The estimate is intentionally coarse so we avoid having to pull in heavy
libraries.  We mainly want to log approximate prompt sizes for debugging.
"""

import math

# Roughly assume 4 characters per token which works well enough for short text.

def estimate_tokens(text: str) -> int:
    """Return a naive token count approximation."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))
