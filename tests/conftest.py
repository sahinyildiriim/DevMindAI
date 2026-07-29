"""Shared pytest fixtures.

The settings cache is process-wide, so it is cleared before every test to
keep environment-driven test cases independent of each other.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from devmind.core.config import get_settings
from devmind.infrastructure.persistence import SqliteDatabase


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Reset the cached settings around each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    """Open an initialised knowledge base backed by a real file."""
    instance = SqliteDatabase(tmp_path / "knowledge" / "devmind.db")
    instance.initialize()
    yield instance
    instance.close()
