"""Unit tests for the parser registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.application.interfaces import DocumentParser
from devmind.core.config import DocumentConfig
from devmind.core.exceptions import ConfigurationError
from devmind.domain.exceptions import DocumentTooLargeError, UnsupportedFormatError
from devmind.domain.value_objects import DocumentFormat
from devmind.infrastructure.parsers import (
    DocxParser,
    MarkdownParser,
    ParserRegistry,
    PdfParser,
    TextParser,
    build_parser_registry,
)

SIZE_LIMIT = 1024 * 1024


@pytest.fixture
def registry() -> ParserRegistry:
    return build_parser_registry(DocumentConfig(max_file_size_mb=1))


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("guide.pdf", PdfParser),
        ("guide.docx", DocxParser),
        ("guide.md", MarkdownParser),
        ("guide.markdown", MarkdownParser),
        ("guide.txt", TextParser),
        ("GUIDE.PDF", PdfParser),
    ],
)
def test_get_parser_resolves_every_supported_extension(
    registry: ParserRegistry, file_name: str, expected: type[DocumentParser]
) -> None:
    assert isinstance(registry.get_parser(Path(file_name)), expected)


def test_get_parser_rejects_unsupported_extensions(registry: ParserRegistry) -> None:
    with pytest.raises(UnsupportedFormatError, match="No parser is registered"):
        registry.get_parser(Path("spreadsheet.xlsx"))


def test_supported_extensions_match_the_domain_formats(registry: ParserRegistry) -> None:
    assert registry.supported_extensions == DocumentFormat.supported_extensions()


def test_registry_applies_the_configured_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "oversized.txt"
    source.write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
    registry = build_parser_registry(DocumentConfig(max_file_size_mb=1))

    with pytest.raises(DocumentTooLargeError):
        registry.get_parser(source).parse(source)


def test_registry_rejects_conflicting_parsers() -> None:
    with pytest.raises(ConfigurationError, match="claimed by both"):
        ParserRegistry((TextParser(SIZE_LIMIT), TextParser(SIZE_LIMIT)))


def test_registry_rejects_an_empty_parser_set() -> None:
    with pytest.raises(ConfigurationError, match="At least one parser"):
        ParserRegistry(())


def test_registry_accepts_a_custom_parser_set() -> None:
    registry = ParserRegistry((TextParser(SIZE_LIMIT),))

    assert registry.supported_extensions == (".txt",)
    with pytest.raises(UnsupportedFormatError):
        registry.get_parser(Path("guide.pdf"))
