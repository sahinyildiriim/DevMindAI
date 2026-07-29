"""The set of document formats DevMind AI is able to ingest.

This enum is the single source of truth for supported file types: both
the parsers and the ingestion configuration derive their behaviour from
it, so adding a format never requires touching several modules.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final

from devmind.domain.exceptions import UnsupportedFormatError

__all__ = ["DocumentFormat"]


class DocumentFormat(StrEnum):
    """A supported document format, identified by its file extensions."""

    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"

    @property
    def extensions(self) -> tuple[str, ...]:
        """File extensions bound to this format, lowercase and dotted."""
        return _FORMAT_EXTENSIONS[self]

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        """Return every supported extension, sorted alphabetically."""
        return tuple(sorted(_EXTENSION_INDEX))

    @classmethod
    def from_extension(cls, extension: str) -> DocumentFormat:
        """Resolve the format bound to a file extension.

        Args:
            extension: Extension with or without a leading dot; the
                lookup is case-insensitive.

        Returns:
            The matching :class:`DocumentFormat`.

        Raises:
            UnsupportedFormatError: If no format claims the extension.
        """
        normalized = extension.strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        try:
            return _EXTENSION_INDEX[normalized]
        except KeyError:
            raise UnsupportedFormatError(
                f"Unsupported file extension {extension!r}. "
                f"Supported extensions: {', '.join(cls.supported_extensions())}."
            ) from None

    @classmethod
    def from_path(cls, source: Path) -> DocumentFormat:
        """Resolve the format of a file from its path.

        Args:
            source: Path to inspect; only the suffix is considered.

        Returns:
            The matching :class:`DocumentFormat`.

        Raises:
            UnsupportedFormatError: If the suffix is unknown or missing.
        """
        return cls.from_extension(source.suffix)


_FORMAT_EXTENSIONS: Final[dict[DocumentFormat, tuple[str, ...]]] = {
    DocumentFormat.PDF: (".pdf",),
    DocumentFormat.DOCX: (".docx",),
    DocumentFormat.MARKDOWN: (".md", ".markdown"),
    DocumentFormat.TEXT: (".txt",),
}

_EXTENSION_INDEX: Final[dict[str, DocumentFormat]] = {
    extension: document_format
    for document_format, extensions in _FORMAT_EXTENSIONS.items()
    for extension in extensions
}
