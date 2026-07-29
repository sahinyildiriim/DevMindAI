"""Base exception hierarchy shared by every layer of DevMind AI.

Only cross-cutting errors live here. Layer specific exceptions must be
declared inside their own layer and inherit from :class:`DevMindError`,
so that a single ``except DevMindError`` clause can guard the
application boundary.
"""

from __future__ import annotations


class DevMindError(Exception):
    """Root of every exception intentionally raised by DevMind AI."""


class ConfigurationError(DevMindError):
    """Raised when configuration is missing, malformed or out of range."""
