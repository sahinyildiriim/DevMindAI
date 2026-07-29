"""Translation between database rows and domain objects.

Column lists live here as well, so a change to the ``documents`` table
is made in one place instead of in every query that reads it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Final

from devmind.core.exceptions import DevMindError
from devmind.domain.entities.document_chunk import DocumentChunk
from devmind.domain.exceptions import StorageError
from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.domain.value_objects.document_format import DocumentFormat
from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = [
    "DOCUMENT_COLUMNS",
    "JOINED_DOCUMENT_COLUMNS",
    "document_values",
    "path_key",
    "to_document_chunk",
    "to_document_metadata",
]

_DOCUMENT_FIELDS: Final[tuple[str, ...]] = (
    "source_path",
    "document_format",
    "size_bytes",
    "checksum",
    "modified_at",
    "title",
    "author",
    "page_count",
)

DOCUMENT_COLUMNS: Final[str] = ", ".join(_DOCUMENT_FIELDS)
"""Document columns as selected from the ``documents`` table alone."""

JOINED_DOCUMENT_COLUMNS: Final[str] = ", ".join(f"d.{field}" for field in _DOCUMENT_FIELDS)
"""Document columns as selected through the ``d`` alias in a join."""


def path_key(source_path: Path) -> str:
    """Return the stored representation of a document path.

    Args:
        source_path: Path of a document. Parsers hand over absolute
            paths, and callers are expected to do the same, since the
            path is the identity of a document.

    Returns:
        The path as stored in the ``source_path`` column.
    """
    return str(source_path)


def document_values(metadata: DocumentMetadata) -> tuple[object, ...]:
    """Flatten document metadata into bind parameters.

    The order matches :data:`DOCUMENT_COLUMNS`.

    Args:
        metadata: The metadata to store.

    Returns:
        The values to bind, in column order.
    """
    return (
        path_key(metadata.source_path),
        metadata.document_format.value,
        metadata.size_bytes,
        metadata.checksum,
        metadata.modified_at.isoformat(),
        metadata.title,
        metadata.author,
        metadata.page_count,
    )


def to_document_metadata(row: sqlite3.Row) -> DocumentMetadata:
    """Rebuild document metadata from a row.

    Args:
        row: A row exposing the document columns.

    Returns:
        The reconstructed metadata.

    Raises:
        StorageError: If the row holds values the domain rejects.
    """
    try:
        return DocumentMetadata(
            source_path=Path(row["source_path"]),
            document_format=DocumentFormat(row["document_format"]),
            size_bytes=row["size_bytes"],
            checksum=row["checksum"],
            modified_at=datetime.fromisoformat(row["modified_at"]),
            title=row["title"],
            author=row["author"],
            page_count=row["page_count"],
        )
    except (ValueError, TypeError, DevMindError) as exc:
        raise StorageError(f"Stored document '{row['source_path']}' is corrupt: {exc}") from exc


def to_document_chunk(row: sqlite3.Row, metadata: DocumentMetadata | None = None) -> DocumentChunk:
    """Rebuild a chunk from a row joining ``chunks`` and ``documents``.

    Args:
        row: A row exposing the chunk columns and the document columns.
        metadata: Metadata of the document the row belongs to. Callers
            reading several chunks of the same document pass it in, so
            that the shared - and immutable - metadata is rebuilt once
            instead of once per row.

    Returns:
        The reconstructed chunk, carrying its document metadata.

    Raises:
        StorageError: If the row holds values the domain rejects.
    """
    resolved = metadata if metadata is not None else to_document_metadata(row)
    try:
        return DocumentChunk(
            chunk_id=ChunkId(row["chunk_id"]),
            content=row["content"],
            index=row["chunk_index"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            metadata=resolved,
        )
    except (ValueError, TypeError, DevMindError) as exc:
        raise StorageError(f"Stored chunk '{row['chunk_id']}' is corrupt: {exc}") from exc
