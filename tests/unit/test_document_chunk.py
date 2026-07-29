"""Unit tests for :mod:`devmind.domain.entities.document_chunk`."""

from __future__ import annotations

import pytest

from devmind.core.exceptions import DevMindError
from devmind.domain.entities import DocumentChunk
from devmind.domain.value_objects import ChunkId
from tests.factories import CHECKSUM, make_metadata

_CONTENT = "Endpoint routing matches requests."


def make_chunk(**overrides: object) -> DocumentChunk:
    defaults: dict[str, object] = {
        "chunk_id": ChunkId.for_document(CHECKSUM, 0),
        "content": _CONTENT,
        "index": 0,
        "start_offset": 10,
        "end_offset": 10 + len(_CONTENT),
        "metadata": make_metadata(),
    }
    return DocumentChunk(**(defaults | overrides))  # type: ignore[arg-type]


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
