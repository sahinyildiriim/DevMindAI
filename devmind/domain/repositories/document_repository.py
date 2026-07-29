"""Persistence contract for indexed documents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = ["DocumentRepository"]


class DocumentRepository(ABC):
    """Stores the documents that make up the knowledge base.

    A document is identified by its source path: re-indexing the same
    file updates the existing record instead of creating a second one,
    while the checksum carried by the metadata tells whether its content
    actually changed.
    """

    @abstractmethod
    def save(self, metadata: DocumentMetadata) -> None:
        """Insert a document, or update it when its path is known.

        Args:
            metadata: Description of the document to store. Its
                ``source_path`` must be absolute.

        Raises:
            StorageError: If the document cannot be written.
        """

    @abstractmethod
    def get(self, source_path: Path) -> DocumentMetadata | None:
        """Read a document by its source path.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The stored metadata, or ``None`` when the path is unknown.

        Raises:
            StorageError: If the document cannot be read.
        """

    @abstractmethod
    def list_all(self) -> tuple[DocumentMetadata, ...]:
        """Read every stored document, ordered by source path.

        Returns:
            The stored documents.

        Raises:
            StorageError: If the documents cannot be read.
        """

    @abstractmethod
    def delete(self, source_path: Path) -> bool:
        """Remove a document and everything derived from it.

        Args:
            source_path: Absolute path of the document.

        Returns:
            ``True`` when a document was removed, ``False`` when the
            path was unknown.

        Raises:
            StorageError: If the document cannot be removed.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the number of stored documents.

        Raises:
            StorageError: If the documents cannot be counted.
        """
