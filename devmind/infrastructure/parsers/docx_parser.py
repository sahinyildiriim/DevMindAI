"""DOCX parser adapter built on python-docx."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from devmind.domain.value_objects.document_format import DocumentFormat
from devmind.infrastructure.parsers.base import ExtractedContent, FileDocumentParser
from devmind.infrastructure.parsers.text_utils import clean_optional

__all__ = ["DocxParser"]

_CELL_SEPARATOR = " | "


class DocxParser(FileDocumentParser):
    """Extracts paragraphs, tables and core properties of a DOCX file."""

    @property
    def document_format(self) -> DocumentFormat:
        """Format handled by this parser."""
        return DocumentFormat.DOCX

    def extract(self, source: Path) -> ExtractedContent:
        """Extract text and core properties from a DOCX document.

        Args:
            source: Absolute path of the validated DOCX file.

        Returns:
            The document text in reading order and its core properties.
        """
        document = docx.Document(str(source))
        blocks = [block for block in self._iter_text_blocks(document) if block]
        properties = document.core_properties
        return ExtractedContent(
            text="\n".join(blocks),
            title=clean_optional(properties.title),
            author=clean_optional(properties.author),
        )

    @classmethod
    def _iter_text_blocks(cls, document: DocxDocument) -> Iterator[str]:
        """Yield the text of every body block in reading order.

        Paragraphs and tables are interleaved in the document body, so
        they are walked through the underlying XML rather than through
        the two separate collections exposed by python-docx.

        Args:
            document: Opened DOCX document.

        Yields:
            The stripped text of each paragraph and table row.
        """
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, document).text.strip()
            elif isinstance(child, CT_Tbl):
                yield from cls._iter_table_rows(Table(child, document))

    @staticmethod
    def _iter_table_rows(table: Table) -> Iterator[str]:
        """Yield one flattened line per table row.

        Args:
            table: Table to flatten.

        Yields:
            The cells of each row joined by a visible separator, which
            keeps tabular relations readable for the language model.
        """
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                yield _CELL_SEPARATOR.join(cells)
