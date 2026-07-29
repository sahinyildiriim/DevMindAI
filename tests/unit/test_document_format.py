"""Unit tests for :mod:`devmind.domain.value_objects.document_format`."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.domain.exceptions import UnsupportedFormatError
from devmind.domain.value_objects import DocumentFormat


@pytest.mark.parametrize(
    ("extension", "expected"),
    [
        (".pdf", DocumentFormat.PDF),
        ("pdf", DocumentFormat.PDF),
        (".PDF", DocumentFormat.PDF),
        ("  .Docx  ", DocumentFormat.DOCX),
        (".md", DocumentFormat.MARKDOWN),
        (".markdown", DocumentFormat.MARKDOWN),
        (".txt", DocumentFormat.TEXT),
    ],
)
def test_from_extension_is_case_and_dot_insensitive(
    extension: str, expected: DocumentFormat
) -> None:
    assert DocumentFormat.from_extension(extension) is expected


@pytest.mark.parametrize("extension", [".rtf", ".xlsx", "", ".", "pdf.exe"])
def test_from_extension_rejects_unknown_types(extension: str) -> None:
    with pytest.raises(UnsupportedFormatError, match="Unsupported file extension"):
        DocumentFormat.from_extension(extension)


def test_error_message_lists_supported_extensions() -> None:
    with pytest.raises(UnsupportedFormatError, match=r"\.pdf"):
        DocumentFormat.from_extension(".rtf")


def test_from_path_uses_the_suffix() -> None:
    assert DocumentFormat.from_path(Path("guides/aspnet.core.md")) is DocumentFormat.MARKDOWN


def test_supported_extensions_is_sorted_and_complete() -> None:
    extensions = DocumentFormat.supported_extensions()

    assert extensions == tuple(sorted(extensions))
    assert set(extensions) == {".docx", ".markdown", ".md", ".pdf", ".txt"}


def test_every_format_declares_lowercase_dotted_extensions() -> None:
    for document_format in DocumentFormat:
        assert document_format.extensions
        assert all(
            extension.startswith(".") and extension == extension.lower()
            for extension in document_format.extensions
        )
