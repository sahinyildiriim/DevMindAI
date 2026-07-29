"""Unit tests for the document parser adapters."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from devmind.application.interfaces import DocumentParser
from devmind.domain.exceptions import (
    DocumentNotFoundError,
    DocumentParseError,
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedFormatError,
)
from devmind.domain.value_objects import DocumentFormat
from devmind.infrastructure.parsers import (
    DocxParser,
    MarkdownParser,
    PdfParser,
    TextParser,
)
from tests.factories import write_docx, write_pdf

SIZE_LIMIT = 1024 * 1024


@pytest.fixture
def pdf_parser() -> PdfParser:
    return PdfParser(SIZE_LIMIT)


@pytest.fixture
def docx_parser() -> DocxParser:
    return DocxParser(SIZE_LIMIT)


@pytest.fixture
def markdown_parser() -> MarkdownParser:
    return MarkdownParser(SIZE_LIMIT)


@pytest.fixture
def text_parser() -> TextParser:
    return TextParser(SIZE_LIMIT)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def test_pdf_parser_extracts_text_and_document_information(
    pdf_parser: PdfParser, tmp_path: Path
) -> None:
    source = write_pdf(
        tmp_path / "routing.pdf",
        ["Endpoint routing matches requests", "Middleware runs in order"],
        title="ASP.NET Core Routing",
        author="Microsoft Learn",
    )

    document = pdf_parser.parse(source)

    assert "Endpoint routing matches requests" in document.content
    assert "Middleware runs in order" in document.content
    assert document.metadata.title == "ASP.NET Core Routing"
    assert document.metadata.author == "Microsoft Learn"
    assert document.metadata.page_count == 2
    assert document.metadata.document_format is DocumentFormat.PDF
    assert len(document.metadata.checksum) == 64


def test_pdf_parser_reports_password_protected_files(pdf_parser: PdfParser, tmp_path: Path) -> None:
    plain = write_pdf(tmp_path / "plain.pdf", ["Secret guidance"])
    writer = PdfWriter(clone_from=PdfReader(plain))
    writer.encrypt("s3cret")
    encrypted = tmp_path / "encrypted.pdf"
    writer.write(str(encrypted))

    with pytest.raises(DocumentParseError, match="password protected"):
        pdf_parser.parse(encrypted)


def test_pdf_parser_reports_corrupted_files(pdf_parser: PdfParser, tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted.pdf"
    corrupted.write_bytes(b"%PDF-1.4\nthis is not a pdf body")

    with pytest.raises(DocumentParseError, match=re.escape("Could not parse 'corrupted.pdf'")):
        pdf_parser.parse(corrupted)


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def test_docx_parser_extracts_paragraphs_tables_and_properties(
    docx_parser: DocxParser, tmp_path: Path
) -> None:
    source = write_docx(
        tmp_path / "architecture.docx",
        ["Clean Architecture keeps the domain independent."],
        table_rows=[["Layer", "Responsibility"], ["Domain", "Business rules"]],
        trailing_paragraphs=["The dependency rule points inwards."],
        title=".NET Architecture Guide",
        author="Microsoft",
    )

    document = docx_parser.parse(source)

    assert "Clean Architecture keeps the domain independent." in document.content
    assert "Layer | Responsibility" in document.content
    assert "Domain | Business rules" in document.content
    assert document.metadata.title == ".NET Architecture Guide"
    assert document.metadata.author == "Microsoft"
    assert document.metadata.page_count is None


def test_docx_parser_preserves_reading_order(docx_parser: DocxParser, tmp_path: Path) -> None:
    source = write_docx(
        tmp_path / "ordered.docx",
        ["Before the table"],
        table_rows=[["Inside the table"]],
        trailing_paragraphs=["After the table"],
    )

    content = docx_parser.parse(source).content

    assert content.index("Before the table") < content.index("Inside the table")
    assert content.index("Inside the table") < content.index("After the table")


def test_docx_parser_reports_corrupted_files(docx_parser: DocxParser, tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted.docx"
    corrupted.write_bytes(b"not a zip archive")

    with pytest.raises(DocumentParseError, match=re.escape("Could not parse 'corrupted.docx'")):
        docx_parser.parse(corrupted)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def test_markdown_parser_strips_syntax_and_reads_front_matter(
    markdown_parser: MarkdownParser, tmp_path: Path
) -> None:
    source = tmp_path / "minimal-apis.md"
    source.write_text(
        "---\n"
        "title: Minimal APIs\n"
        "author: Microsoft Learn\n"
        "---\n"
        "\n"
        "# Minimal APIs\n"
        "\n"
        "Use **MapGet** to declare an [endpoint](https://learn.microsoft.com).\n"
        "\n"
        "- Fast\n"
        "- Simple\n",
        encoding="utf-8",
    )

    document = markdown_parser.parse(source)

    assert document.metadata.title == "Minimal APIs"
    assert document.metadata.author == "Microsoft Learn"
    assert "Use MapGet to declare an endpoint." in document.content
    assert "**" not in document.content
    assert "https://learn.microsoft.com" not in document.content
    assert "Fast" in document.content


def test_markdown_parser_falls_back_to_the_first_heading(
    markdown_parser: MarkdownParser, tmp_path: Path
) -> None:
    source = tmp_path / "guide.md"
    source.write_text("## Dependency Injection\n\nRegister services.\n", encoding="utf-8")

    document = markdown_parser.parse(source)

    assert document.metadata.title == "Dependency Injection"
    assert document.metadata.author is None


def test_markdown_parser_keeps_a_colon_line_that_is_not_front_matter(
    markdown_parser: MarkdownParser, tmp_path: Path
) -> None:
    source = tmp_path / "note.md"
    source.write_text("Note: read the prerequisites first.\n\nThen continue.\n", encoding="utf-8")

    content = markdown_parser.parse(source).content

    assert "Note: read the prerequisites first." in content
    assert "Then continue." in content


def test_markdown_parser_keeps_code_and_tables_but_drops_scripts(
    markdown_parser: MarkdownParser, tmp_path: Path
) -> None:
    source = tmp_path / "sample.markdown"
    source.write_text(
        "# Sample\n"
        "\n"
        "| Verb | Route |\n"
        "| ---- | ----- |\n"
        "| GET  | /api  |\n"
        "\n"
        "```csharp\n"
        'app.MapGet("/api", () => Results.Ok());\n'
        "```\n"
        "\n"
        "<script>alert('tracker');</script>\n",
        encoding="utf-8",
    )

    content = markdown_parser.parse(source).content

    assert "app.MapGet" in content
    assert "Verb" in content
    assert "alert" not in content


# --------------------------------------------------------------------------- #
# Plain text
# --------------------------------------------------------------------------- #
def test_text_parser_reads_content_and_derives_a_title(
    text_parser: TextParser, tmp_path: Path
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Deployment checklist\n\nRun the migrations.\n", encoding="utf-8")

    document = text_parser.parse(source)

    assert document.metadata.title == "Deployment checklist"
    assert "Run the migrations." in document.content
    assert document.metadata.document_format is DocumentFormat.TEXT


def test_text_parser_falls_back_to_legacy_encodings(
    text_parser: TextParser, tmp_path: Path
) -> None:
    source = tmp_path / "legacy.txt"
    source.write_bytes("Ölçüm günlüğü".encode("cp1254"))

    assert "Ölçüm günlüğü" in text_parser.parse(source).content


def test_text_parser_normalizes_whitespace(text_parser: TextParser, tmp_path: Path) -> None:
    source = tmp_path / "messy.txt"
    source.write_bytes(b"\r\n\r\nTitle   \r\n\r\n\r\n\r\nBody\t\r\n\r\n")

    assert text_parser.parse(source).content == "Title\n\nBody"


# --------------------------------------------------------------------------- #
# Behaviour shared by every parser
# --------------------------------------------------------------------------- #
@pytest.fixture(
    params=[
        (PdfParser, ".pdf"),
        (DocxParser, ".docx"),
        (MarkdownParser, ".md"),
        (TextParser, ".txt"),
    ],
    ids=["pdf", "docx", "markdown", "text"],
)
def parser_and_extension(request: pytest.FixtureRequest) -> tuple[DocumentParser, str]:
    parser_type, extension = request.param
    return parser_type(SIZE_LIMIT), extension


def test_parser_rejects_missing_files(
    parser_and_extension: tuple[DocumentParser, str], tmp_path: Path
) -> None:
    parser, extension = parser_and_extension

    with pytest.raises(DocumentNotFoundError):
        parser.parse(tmp_path / f"absent{extension}")


def test_parser_rejects_directories(
    parser_and_extension: tuple[DocumentParser, str], tmp_path: Path
) -> None:
    parser, extension = parser_and_extension
    directory = tmp_path / f"folder{extension}"
    directory.mkdir()

    with pytest.raises(DocumentNotFoundError, match="is not a file"):
        parser.parse(directory)


def test_parser_rejects_foreign_extensions(
    parser_and_extension: tuple[DocumentParser, str], tmp_path: Path
) -> None:
    parser, _ = parser_and_extension
    foreign = tmp_path / "report.rtf"
    foreign.write_text("content", encoding="utf-8")

    with pytest.raises(UnsupportedFormatError):
        parser.parse(foreign)


def test_parser_enforces_the_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_text("x" * 2048, encoding="utf-8")

    with pytest.raises(DocumentTooLargeError, match="exceeds the limit"):
        TextParser(1024).parse(source)


def test_parser_rejects_documents_without_text(text_parser: TextParser, tmp_path: Path) -> None:
    source = tmp_path / "blank.txt"
    source.write_text("   \n\n", encoding="utf-8")

    with pytest.raises(EmptyDocumentError, match=re.escape("blank.txt")):
        text_parser.parse(source)


def test_parser_rejects_a_non_positive_size_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        TextParser(0)


def test_parsers_accept_uppercase_extensions(text_parser: TextParser, tmp_path: Path) -> None:
    source = tmp_path / "README.TXT"
    source.write_text("Uppercase extensions are still text files.", encoding="utf-8")

    assert text_parser.supports(source)
    assert "Uppercase" in text_parser.parse(source).content


def test_checksum_identifies_identical_content(text_parser: TextParser, tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    third = tmp_path / "c.txt"
    first.write_text("Same content", encoding="utf-8")
    second.write_text("Same content", encoding="utf-8")
    third.write_text("Other content", encoding="utf-8")

    checksums = {text_parser.parse(path).metadata.checksum for path in (first, second)}
    assert len(checksums) == 1
    assert text_parser.parse(third).metadata.checksum not in checksums


def test_metadata_records_the_resolved_path_and_size(
    text_parser: TextParser, tmp_path: Path
) -> None:
    source = tmp_path / "sized.txt"
    source.write_text("12345", encoding="utf-8")

    metadata = text_parser.parse(source).metadata

    assert metadata.source_path.is_absolute()
    assert metadata.size_bytes == 5
    assert metadata.modified_at.tzinfo is not None
