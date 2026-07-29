"""Unit tests for the SQLite metadata repository."""

from __future__ import annotations

import pytest

from devmind.infrastructure.persistence import SCHEMA_VERSION, SqliteDatabase
from devmind.infrastructure.persistence.metadata_repository import SqliteMetadataRepository
from devmind.infrastructure.persistence.schema import SCHEMA_VERSION_KEY


@pytest.fixture
def repository(database: SqliteDatabase) -> SqliteMetadataRepository:
    return SqliteMetadataRepository(database)


def test_a_value_is_read_back_unchanged(repository: SqliteMetadataRepository) -> None:
    repository.put("embedding_model", "all-minilm-l6-v2")

    assert repository.get("embedding_model") == "all-minilm-l6-v2"


def test_unknown_keys_read_as_none(repository: SqliteMetadataRepository) -> None:
    assert repository.get("never_written") is None


def test_writing_twice_replaces_the_value(repository: SqliteMetadataRepository) -> None:
    repository.put("last_run", "2026-07-01")
    repository.put("last_run", "2026-07-29")

    assert repository.get("last_run") == "2026-07-29"


def test_the_schema_version_is_visible_alongside_the_entries(
    repository: SqliteMetadataRepository,
) -> None:
    repository.put("embedding_model", "all-minilm-l6-v2")

    assert repository.items() == {
        SCHEMA_VERSION_KEY: SCHEMA_VERSION,
        "embedding_model": "all-minilm-l6-v2",
    }


def test_deleting_reports_whether_anything_was_removed(
    repository: SqliteMetadataRepository,
) -> None:
    repository.put("temporary", "value")

    assert repository.delete("temporary") is True
    assert repository.delete("temporary") is False


@pytest.mark.parametrize("key", ["", "   "])
def test_blank_keys_are_refused(repository: SqliteMetadataRepository, key: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        repository.put(key, "value")


def test_empty_values_are_allowed(repository: SqliteMetadataRepository) -> None:
    repository.put("optional", "")

    assert repository.get("optional") == ""
