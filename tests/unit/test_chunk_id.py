"""Unit tests for :mod:`devmind.domain.value_objects.chunk_id`."""

from __future__ import annotations

import pytest

from devmind.core.exceptions import DevMindError
from devmind.domain.value_objects import ChunkId
from tests.factories import CHECKSUM


def test_identifier_combines_the_document_and_the_position() -> None:
    chunk_id = ChunkId.for_document(CHECKSUM, 7)

    assert chunk_id.value == "a1b2c3d4e5f60718-0007"
    assert str(chunk_id) == "a1b2c3d4e5f60718-0007"


def test_identifier_is_deterministic() -> None:
    assert ChunkId.for_document(CHECKSUM, 3) == ChunkId.for_document(CHECKSUM, 3)


def test_identifier_is_case_insensitive_about_the_checksum() -> None:
    assert ChunkId.for_document(CHECKSUM.upper(), 3) == ChunkId.for_document(CHECKSUM, 3)


def test_position_changes_the_identifier() -> None:
    assert ChunkId.for_document(CHECKSUM, 1) != ChunkId.for_document(CHECKSUM, 2)


def test_document_changes_the_identifier() -> None:
    other = "f" * 64

    assert ChunkId.for_document(other, 1) != ChunkId.for_document(CHECKSUM, 1)


def test_identifiers_of_a_document_sort_by_position() -> None:
    identifiers = [ChunkId.for_document(CHECKSUM, index).value for index in range(11)]

    assert identifiers == sorted(identifiers)


def test_large_indexes_stay_well_formed() -> None:
    assert ChunkId.for_document(CHECKSUM, 123_456).value == "a1b2c3d4e5f60718-123456"


def test_negative_index_is_rejected() -> None:
    with pytest.raises(DevMindError, match="must not be negative"):
        ChunkId.for_document(CHECKSUM, -1)


def test_short_checksum_is_rejected() -> None:
    with pytest.raises(DevMindError, match="at least 16 characters"):
        ChunkId.for_document("abc", 0)


@pytest.mark.parametrize("value", ["", "not-an-id", "a1b2c3d4e5f60718", "zzzz-0001", "0007"])
def test_malformed_identifiers_are_rejected(value: str) -> None:
    with pytest.raises(DevMindError, match="Malformed chunk id"):
        ChunkId(value)


def test_identifier_is_immutable() -> None:
    chunk_id = ChunkId.for_document(CHECKSUM, 0)

    with pytest.raises(AttributeError):
        chunk_id.value = "a1b2c3d4e5f60718-0001"  # type: ignore[misc]
