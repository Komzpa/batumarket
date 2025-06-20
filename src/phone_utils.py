import re
from log_utils import get_logger

log = get_logger().bind(module=__name__)

_GE_PREFIX = "995"


def format_georgian(phone: str) -> str:
    """Return ``phone`` in ``+995...`` format if possible."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return phone
    if digits.startswith(_GE_PREFIX):
        normalized = digits
    elif digits.startswith("0"):
        normalized = _GE_PREFIX + digits.lstrip("0")
    elif len(digits) == 9:
        normalized = _GE_PREFIX + digits
    else:
        log.debug("Unrecognized phone", phone=phone)
        return "+" + digits
    return "+" + normalized
