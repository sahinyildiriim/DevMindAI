"""Cross-cutting concerns: configuration, logging and base exceptions.

This package is dependency-free with respect to the other layers; every
layer may import from it, but it must never import from ``domain``,
``application``, ``infrastructure`` or ``presentation``.
"""

from devmind.core.config import Settings, get_settings
from devmind.core.exceptions import ConfigurationError, DevMindError
from devmind.core.logger import configure_logging, get_logger

__all__ = [
    "ConfigurationError",
    "DevMindError",
    "Settings",
    "configure_logging",
    "get_logger",
    "get_settings",
]
