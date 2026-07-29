"""Descriptive facts about a source document.

The metadata describes the *file* and whatever the format itself
declares (title, author, page count). Statistics derived from the
extracted text live on :class:`~devmind.domain.entities.ParsedDocument`
instead, so a single fact is never stored in two places.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from devmind.core.exceptions import DevMindError
from devmind.domain.value_objects.document_format import DocumentFormat

__all__ = ["DocumentMetadata"]

_CHECKSUM_LENGTH = 64


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Immutable description of an ingested document.

    Attributes:
        source_path: Absolute path the document was read from.
        document_format: Format the document was parsed as.
        size_bytes: Size of the source file on disk.
        checksum: SHA-256 hex digest of the file, used to detect
            duplicates and content changes between ingestion runs.
        modified_at: Last modification time of the file, in UTC.
        title: Title declared by the document, when available.
        author: Author declared by the document, when available.
        page_count: Number of pages, for paginated formats only.
    """

    source_path: Path
    document_format: DocumentFormat
    size_bytes: int
    checksum: str
    modified_at: datetime
    title: str | None = None
    author: str | None = None
    page_count: int | None = None

    def __post_init__(self) -> None:
        """Validate the invariants of the metadata.

        Raises:
            DevMindError: If any field holds an impossible value.
        """
        if self.size_bytes < 0:
            raise DevMindError("Document size must not be negative.")
        if len(self.checksum) != _CHECKSUM_LENGTH:
            raise DevMindError(
                f"Checksum must be a {_CHECKSUM_LENGTH} character SHA-256 hex digest."
            )
        if self.modified_at.tzinfo is None:
            raise DevMindError("Modification time must be timezone aware.")
        if self.page_count is not None and self.page_count <= 0:
            raise DevMindError("Page count must be greater than zero when known.")

    @property
    def file_name(self) -> str:
        """Name of the source file, including its extension."""
        return self.source_path.name

    @property
    def display_title(self) -> str:
        """Human readable label: the declared title, or the file name."""
        return self.title or self.file_name
