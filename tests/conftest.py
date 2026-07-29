"""Shared pytest fixtures.

The settings cache is process-wide, so it is cleared before every test to
keep environment-driven test cases independent of each other.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from devmind.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Reset the cached settings around each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
