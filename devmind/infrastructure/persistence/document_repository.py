"""SQLite implementation of :class:`DocumentRepository`."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from devmind.core.logger import get_logger
from devmind.domain.repositories.document_repository import DocumentRepository
from devmind.domain.value_objects.document_metadata import DocumentMetadata
from devmind.infrastructure.persistence.database import SqliteDatabase
from devmind.infrastructure.persistence.mappers import (
    DOCUMENT_COLUMNS,
    document_values,
    path_key,
    to_document_metadata,
)

__all__ = ["SqliteDocumentRepository"]

_logger = get_logger(__name__)

_UPSERT: Final[str] = f"""
    INSERT INTO documents ({DOCUMENT_COLUMNS})
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (source_path) DO UPDATE SET
        document_format = excluded.document_format,
        size_bytes      = excluded.size_bytes,
        checksum        = excluded.checksum,
        modified_at     = excluded.modified_at,
        title           = excluded.title,
        author          = excluded.author,
        page_count      = excluded.page_count
"""


class SqliteDocumentRepository(DocumentRepository):
    """Stores documents in the SQLite knowledge base."""

    def __init__(self, database: SqliteDatabase) -> None:
        """Initialise the repository.

        Args:
            database: Gateway to the knowledge base.
        """
        self._database = database

    def save(self, metadata: DocumentMetadata) -> None:
        """Insert a document, or update it when its path is known.

        Updating keeps the internal row identity, so chunks already
        attached to the document survive. Replacing them after a content
        change is the caller's responsibility.

        Args:
            metadata: Description of the document to store.

        Raises:
            StorageError: If the document cannot be written.
        """
        self._database.execute(_UPSERT, document_values(metadata))
        _logger.debug("Stored document '%s'", metadata.file_name)

    def get(self, source_path: Path) -> DocumentMetadata | None:
        """Read a document by its source path.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The stored metadata, or ``None`` when the path is unknown.

        Raises:
            StorageError: If the document cannot be read.
        """
        row = self._database.fetch_one(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents WHERE source_path = ?",
            (path_key(source_path),),
        )
        return to_document_metadata(row) if row is not None else None

    def list_all(self) -> tuple[DocumentMetadata, ...]:
        """Read every stored document, ordered by source path.

        Returns:
            The stored documents.

        Raises:
            StorageError: If the documents cannot be read.
        """
        rows = self._database.fetch_all(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents ORDER BY source_path"
        )
        return tuple(to_document_metadata(row) for row in rows)

    def delete(self, source_path: Path) -> bool:
        """Remove a document, its chunks and their embeddings.

        Args:
            source_path: Absolute path of the document.

        Returns:
            ``True`` when a document was removed.

        Raises:
            StorageError: If the document cannot be removed.
        """
        removed = self._database.execute(
            "DELETE FROM documents WHERE source_path = ?", (path_key(source_path),)
        )
        if removed:
            _logger.info("Removed document '%s' from the knowledge base", source_path.name)
        return removed > 0

    def count(self) -> int:
        """Return the number of stored documents.

        Raises:
            StorageError: If the documents cannot be counted.
        """
        row = self._database.fetch_one("SELECT COUNT(*) AS total FROM documents")
        return int(row["total"]) if row is not None else 0
