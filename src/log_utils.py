import logging
import sys
import os

try:
    import structlog
    _has_structlog = True
except Exception:
    structlog = None
    _has_structlog = False

LOGFILE = "errors.log"
_logger_initialized = False
_logger = None

def init_logger(truncate=False):
    """Initialize logger writing to ``LOGFILE``.

    Falls back to the standard logging module if ``structlog`` isn't
    available so the scripts can still run in minimal environments.
    """
    global _logger_initialized, _logger
    if _logger_initialized:
        return _logger

    mode = "w" if truncate else "a"
    level = logging.INFO if os.getenv("TEST_MODE") == "1" else logging.ERROR
    logging.basicConfig(
        handlers=[logging.FileHandler(LOGFILE, mode=mode)],
        level=level,
        format="%(message)s",
    )
    # Use the standard library logging as the backend so all log messages end
    # up in ``LOGFILE`` instead of the default stderr output.  Without this
    # ``logger_factory`` structlog prints directly to stdout which polluted the
    # generated intermediate markdown files.
    if _has_structlog:
        structlog.configure(
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.make_filtering_bound_logger(level),
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
        )
        logger = structlog.get_logger()
    else:
        class _Wrapper:
            def __init__(self, logger):
                self._logger = logger

            def bind(self, **_kw):
                return self

            def _format(self, msg, **kw):
                if kw:
                    extras = " ".join(f"{k}={v}" for k, v in kw.items())
                    return f"{msg} {extras}"
                return msg

            def info(self, msg, **kw):
                self._logger.info(self._format(msg, **kw))

            def error(self, msg, **kw):
                self._logger.error(self._format(msg, **kw))

            def exception(self, msg, **kw):
                self._logger.exception(self._format(msg, **kw))

            def debug(self, msg, **kw):
                self._logger.debug(self._format(msg, **kw))

        logger = _Wrapper(logging.getLogger(__name__))
    _logger = logger
    _logger_initialized = True
    return _logger

def get_logger():
    return init_logger()

def install_excepthook(logger):
    """Log uncaught exceptions with provided logger."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception
