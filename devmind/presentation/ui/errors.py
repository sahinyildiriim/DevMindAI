"""Shared handling for the domain failures a page can encounter.

Every exception a page catches already carries actionable text - a
Foundry Local error even includes a "foundry service start" hint - so
displaying it is only ever a matter of showing that same text, never
inventing new wording. What was missing before this existed is an
operator-visible trail: caught here, a failure reached the user but left
no trace in the log file.
"""

from __future__ import annotations

from devmind.core.logger import get_logger

__all__ = ["log_and_format"]

_logger = get_logger(__name__)


def log_and_format(context: str, exc: Exception) -> str:
    """Log a caught failure and return its message for display.

    Args:
        context: Short description of the operation that failed, for
            the log line only - never shown to the user.
        exc: The failure a page caught.

    Returns:
        ``str(exc)``, unchanged.
    """
    _logger.warning("%s failed: %s", context, exc)
    return str(exc)
