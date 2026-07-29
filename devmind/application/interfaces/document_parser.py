"""Ports for turning a source file into a :class:`ParsedDocument`.

These abstractions are owned by the application layer and implemented by
the infrastructure layer, so use cases depend on the contract rather
than on pypdf, python-docx or the file system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from devmind.domain.entities.parsed_document import ParsedDocument
from devmind.domain.value_objects.document_format import DocumentFormat

__all__ = ["DocumentParser", "DocumentParserRegistry"]


class DocumentParser(ABC):
    """Extracts text and metadata from a single document format."""

    @property
    @abstractmethod
    def document_format(self) -> DocumentFormat:
        """Format this parser is responsible for."""

    @abstractmethod
    def parse(self, source: Path) -> ParsedDocument:
        """Read a document and return its text and metadata.

        Args:
            source: Path of the file to parse.

        Returns:
            The parsed document.

        Raises:
            DocumentNotFoundError: If the path does not point to a file.
            UnsupportedFormatError: If the file type does not match
                :attr:`document_format`.
            DocumentTooLargeError: If the file exceeds the size limit.
            DocumentParseError: If the file cannot be read or contains
                no extractable text.
        """

    def supports(self, source: Path) -> bool:
        """Report whether this parser can handle the given file.

        Args:
            source: Path to test; only the suffix is considered.

        Returns:
            ``True`` when the extension belongs to
            :attr:`document_format`.
        """
        return source.suffix.lower() in self.document_format.extensions


class DocumentParserRegistry(ABC):
    """Resolves the parser responsible for a given file."""

    @property
    @abstractmethod
    def supported_extensions(self) -> tuple[str, ...]:
        """Every extension the registered parsers can handle."""

    @abstractmethod
    def get_parser(self, source: Path) -> DocumentParser:
        """Return the parser registered for a file.

        Args:
            source: Path of the file to be parsed.

        Returns:
            The parser bound to the file extension.

        Raises:
            UnsupportedFormatError: If no parser claims the extension.
        """
