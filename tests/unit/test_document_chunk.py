"""Unit tests for :mod:`devmind.domain.entities.document_chunk`."""

from __future__ import annotations

import pytest

from devmind.core.exceptions import DevMindError
from tests.factories import CHECKSUM, CHUNK_CONTENT, make_chunk

_CONTENT = CHUNK_CONTENT


def test_chunk_reports_its_size_and_keeps_the_document_metadata() -> None:
    chunk = make_chunk()

    assert chunk.character_count == len(_CONTENT)
    assert chunk.metadata.file_name == "guide.md"
    assert chunk.metadata.checksum == CHECKSUM


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"content": "   "}, "carries no text"),
        ({"index": -1}, "index must not be negative"),
        ({"start_offset": -1}, "start offset must not be negative"),
        ({"end_offset": 10}, "do not match its content length"),
        ({"end_offset": 500}, "do not match its content length"),
    ],
)
def test_chunk_rejects_inconsistent_values(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(DevMindError, match=message):
        make_chunk(**overrides)


def test_chunk_is_immutable() -> None:
    chunk = make_chunk()

    with pytest.raises(AttributeError):
        chunk.content = "changed"  # type: ignore[misc]
