"""Unit tests for the common parser result model."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from devmind.core.exceptions import DevMindError
from devmind.domain.entities import ParsedDocument
from devmind.domain.exceptions import EmptyDocumentError
from devmind.domain.value_objects import DocumentFormat, DocumentMetadata

_CHECKSUM = "a" * 64
_MODIFIED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def make_metadata(**overrides: object) -> DocumentMetadata:
    defaults: dict[str, object] = {
        "source_path": Path("data/documents/guide.md"),
        "document_format": DocumentFormat.MARKDOWN,
        "size_bytes": 128,
        "checksum": _CHECKSUM,
        "modified_at": _MODIFIED_AT,
    }
    return DocumentMetadata(**(defaults | overrides))  # type: ignore[arg-type]


def test_metadata_exposes_file_name_and_display_title() -> None:
    metadata = make_metadata()

    assert metadata.file_name == "guide.md"
    assert metadata.display_title == "guide.md"
    assert make_metadata(title="Routing").display_title == "Routing"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"size_bytes": -1}, "size must not be negative"),
        ({"checksum": "short"}, "SHA-256"),
        ({"modified_at": datetime(2026, 7, 29, 12, 0)}, "timezone aware"),
        ({"page_count": 0}, "Page count"),
    ],
)
def test_metadata_rejects_impossible_values(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(DevMindError, match=message):
        make_metadata(**overrides)


def test_metadata_is_immutable() -> None:
    metadata = make_metadata()

    with pytest.raises(AttributeError):
        metadata.title = "changed"  # type: ignore[misc]


def test_parsed_document_reports_content_statistics() -> None:
    document = ParsedDocument(content="Minimal APIs are fast", metadata=make_metadata())

    assert document.word_count == 4
    assert document.character_count == 21


@pytest.mark.parametrize("content", ["", "   ", "\n\n\t "])
def test_parsed_document_rejects_blank_content(content: str) -> None:
    with pytest.raises(EmptyDocumentError, match=re.escape("guide.md")):
        ParsedDocument(content=content, metadata=make_metadata())
