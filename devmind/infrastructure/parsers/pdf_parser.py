"""PDF parser adapter built on pypdf."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from devmind.domain.exceptions import DocumentParseError
from devmind.domain.value_objects.document_format import DocumentFormat
from devmind.infrastructure.parsers.base import ExtractedContent, FileDocumentParser
from devmind.infrastructure.parsers.text_utils import clean_optional

__all__ = ["PdfParser"]

_PAGE_SEPARATOR = "\n\n"


class PdfParser(FileDocumentParser):
    """Extracts the text layer and document information of a PDF file."""

    @property
    def document_format(self) -> DocumentFormat:
        """Format handled by this parser."""
        return DocumentFormat.PDF

    def extract(self, source: Path) -> ExtractedContent:
        """Extract text and document information from a PDF.

        Args:
            source: Absolute path of the validated PDF file.

        Returns:
            The concatenated page texts and the embedded metadata.

        Raises:
            DocumentParseError: If the file is protected by a password.
        """
        reader = PdfReader(source)
        self._unlock(reader, source)

        pages = [page.extract_text() or "" for page in reader.pages]
        text = _PAGE_SEPARATOR.join(page for page in pages if page.strip())

        information = reader.metadata
        return ExtractedContent(
            text=text,
            title=clean_optional(information.title if information else None),
            author=clean_optional(information.author if information else None),
            page_count=len(reader.pages) or None,
        )

    @staticmethod
    def _unlock(reader: PdfReader, source: Path) -> None:
        """Open a PDF that is encrypted with an empty owner password.

        Files encrypted with an empty password are common and readable;
        anything else needs a secret DevMind AI does not have.

        Args:
            reader: Reader bound to the source file.
            source: Path used for the error message.

        Raises:
            DocumentParseError: If the file stays locked.
        """
        if not reader.is_encrypted:
            return
        if not reader.decrypt(""):
            raise DocumentParseError(
                f"'{source.name}' is password protected and cannot be indexed."
            )
