"""Centralised logging setup for DevMind AI.

The application configures logging exactly once, at start-up, through
:func:`configure_logging`. Every other module only asks for a logger via
:func:`get_logger` and never touches handlers, which keeps logging
behaviour consistent across the Streamlit UI, ingestion jobs and tests.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from threading import Lock
from typing import Final

from devmind.core.config import LoggingConfig, get_settings

__all__ = ["ROOT_LOGGER_NAME", "configure_logging", "get_logger"]

ROOT_LOGGER_NAME: Final[str] = "devmind"

_LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

# Third party libraries are verbose at DEBUG level and would drown the
# application's own diagnostics.
_NOISY_LOGGERS: Final[tuple[str, ...]] = (
    "httpcore",
    "httpx",
    "openai",
    "urllib3",
    "watchdog",
)

_lock: Final[Lock] = Lock()
_configured: bool = False


def configure_logging(config: LoggingConfig | None = None, *, force: bool = False) -> None:
    """Install console and rotating-file handlers on the root logger.

    The call is idempotent: repeated invocations (for example on every
    Streamlit rerun) are ignored unless ``force`` is set, which prevents
    duplicated log records. When the setup does run, it takes ownership
    of the root logger and replaces any handler already attached to it.

    Args:
        config: Logging section to apply. Defaults to the active settings.
        force: Reconfigure and replace existing handlers when ``True``.

    Raises:
        OSError: If the log directory or file cannot be created.
    """
    global _configured

    with _lock:
        if _configured and not force:
            return

        settings = config if config is not None else get_settings().logging
        settings.directory.mkdir(parents=True, exist_ok=True)

        root = logging.getLogger()
        for handler in tuple(root.handlers):
            root.removeHandler(handler)
            handler.close()

        formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

        file_handler = RotatingFileHandler(
            filename=settings.file_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        if settings.console_enabled:
            console_handler = logging.StreamHandler(stream=sys.stdout)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)

        root.setLevel(settings.level)
        for noisy in _NOISY_LOGGERS:
            logging.getLogger(noisy).setLevel(logging.WARNING)

        logging.captureWarnings(True)
        _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced application logger.

    Args:
        name: Usually ``__name__``. Names outside the ``devmind`` package
            are prefixed automatically so that all application records
            share a single hierarchy.

    Returns:
        The requested :class:`logging.Logger`.
    """
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
