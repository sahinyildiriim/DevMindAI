"""Plain text parser adapter."""

from __future__ import annotations

from pathlib import Path

from devmind.domain.value_objects.document_format import DocumentFormat
from devmind.infrastructure.parsers.base import ExtractedContent, FileDocumentParser
from devmind.infrastructure.parsers.text_utils import derive_title, read_text_file

__all__ = ["TextParser"]


class TextParser(FileDocumentParser):
    """Reads plain text files, tolerating legacy encodings."""

    @property
    def document_format(self) -> DocumentFormat:
        """Format handled by this parser."""
        return DocumentFormat.TEXT

    def extract(self, source: Path) -> ExtractedContent:
        """Read a plain text file.

        Plain text carries no embedded metadata, so the title is derived
        from the first line of the document when it reads like a
        heading.

        Args:
            source: Absolute path of the validated text file.

        Returns:
            The file content and the derived title.
        """
        text = read_text_file(source)
        return ExtractedContent(text=text, title=derive_title(text))
