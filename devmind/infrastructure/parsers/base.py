"""Shared skeleton for file based parser adapters.

:class:`FileDocumentParser` implements everything that does not depend
on the document format - validation, checksumming, metadata assembly,
normalisation, logging and error translation - and leaves a single
:meth:`FileDocumentParser.extract` hook to the concrete parsers.
"""

from __future__ import annotations

import hashlib
import os
from abc import abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Final

from devmind.application.interfaces.document_parser import DocumentParser
from devmind.core.exceptions import DevMindError
from devmind.core.logger import get_logger
from devmind.domain.entities.parsed_document import ParsedDocument
from devmind.domain.exceptions import (
    DocumentNotFoundError,
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedFormatError,
)
from devmind.domain.value_objects.document_metadata import DocumentMetadata
from devmind.infrastructure.parsers.text_utils import normalize_text

__all__ = ["ExtractedContent", "FileDocumentParser"]

_logger = get_logger(__name__)

_CHECKSUM_BLOCK_SIZE: Final[int] = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    """Raw output of a format specific extractor.

    Attributes:
        text: Text as produced by the underlying library, before
            normalisation.
        title: Title declared by the document, when available.
        author: Author declared by the document, when available.
        page_count: Number of pages, for paginated formats only.
    """

    text: str
    title: str | None = None
    author: str | None = None
    page_count: int | None = None


class FileDocumentParser(DocumentParser):
    """Template for parsers that read a document from the file system."""

    def __init__(self, max_file_size_bytes: int) -> None:
        """Initialise the parser.

        Args:
            max_file_size_bytes: Upper bound for accepted files. The
                limit guards the pipeline against exhausting memory on
                an unexpectedly large document.

        Raises:
            ValueError: If the limit is not a positive number of bytes.
        """
        if max_file_size_bytes <= 0:
            raise ValueError("Maximum file size must be greater than zero.")
        self._max_file_size_bytes = max_file_size_bytes

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
        path, stats = self._inspect(source)
        started_at = perf_counter()

        extracted = self._extract_safely(path)
        content = normalize_text(extracted.text)
        metadata = self._build_metadata(path, stats, extracted)
        document = ParsedDocument(content=content, metadata=metadata)

        _logger.info(
            "Parsed %s document '%s': %d characters in %.3fs",
            self.document_format.value,
            metadata.file_name,
            document.character_count,
            perf_counter() - started_at,
        )
        return document

    @abstractmethod
    def extract(self, source: Path) -> ExtractedContent:
        """Extract text and format specific metadata from a file.

        The file is guaranteed to exist, to match this parser's format
        and to respect the configured size limit. Implementations may
        let library specific exceptions escape: they are translated into
        :class:`DocumentParseError` by the template method.

        Args:
            source: Absolute path of the validated file.

        Returns:
            The raw extraction result.
        """

    def _inspect(self, source: Path) -> tuple[Path, os.stat_result]:
        """Validate the source file and return it with its stat result.

        Args:
            source: Path supplied by the caller.

        Returns:
            The resolved path and the ``stat`` result, read once and
            reused for both the size check and the metadata.

        Raises:
            DocumentNotFoundError: If the path does not point to a file.
            UnsupportedFormatError: If the extension does not match.
            DocumentTooLargeError: If the file exceeds the size limit.
        """
        path = source.expanduser().resolve()
        if not self.supports(path):
            raise UnsupportedFormatError(
                f"'{path.name}' is not a {self.document_format.value} document. "
                f"Expected one of: {', '.join(self.document_format.extensions)}."
            )
        try:
            stats = path.stat()
        except OSError as exc:
            raise DocumentNotFoundError(f"Cannot access '{source}': {exc}") from exc
        if not path.is_file():
            raise DocumentNotFoundError(f"'{source}' is not a file.")
        if stats.st_size > self._max_file_size_bytes:
            raise DocumentTooLargeError(
                f"'{path.name}' is {stats.st_size} bytes, which exceeds the "
                f"limit of {self._max_file_size_bytes} bytes."
            )
        return path, stats

    def _extract_safely(self, path: Path) -> ExtractedContent:
        """Run :meth:`extract` and translate third party failures.

        Args:
            path: Absolute path of the validated file.

        Returns:
            The raw extraction result.

        Raises:
            DocumentParseError: If the underlying library fails.
        """
        try:
            return self.extract(path)
        except DevMindError:
            raise
        except Exception as exc:
            _logger.warning("Extraction failed for '%s': %s", path.name, exc)
            raise DocumentParseError(
                f"Could not parse '{path.name}': {type(exc).__name__}: {exc}"
            ) from exc

    def _build_metadata(
        self, path: Path, stats: os.stat_result, extracted: ExtractedContent
    ) -> DocumentMetadata:
        """Assemble the uniform metadata of a parsed document.

        Args:
            path: Absolute path of the file.
            stats: Stat result collected during validation.
            extracted: Format specific extraction result.

        Returns:
            The assembled metadata.
        """
        return DocumentMetadata(
            source_path=path,
            document_format=self.document_format,
            size_bytes=stats.st_size,
            checksum=self._checksum(path),
            modified_at=datetime.fromtimestamp(stats.st_mtime, tz=UTC),
            title=extracted.title,
            author=extracted.author,
            page_count=extracted.page_count,
        )

    @staticmethod
    def _checksum(path: Path) -> str:
        """Compute the SHA-256 digest of a file.

        The file is streamed in blocks so that memory usage stays
        constant regardless of the document size.

        Args:
            path: Absolute path of the file.

        Returns:
            The hex digest.

        Raises:
            DocumentParseError: If the file cannot be read.
        """
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while block := stream.read(_CHECKSUM_BLOCK_SIZE):
                    digest.update(block)
        except OSError as exc:
            raise DocumentParseError(f"Could not read '{path.name}': {exc}") from exc
        return digest.hexdigest()
