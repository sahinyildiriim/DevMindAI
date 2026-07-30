"""SQLite implementation of :class:`ChunkRepository`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from devmind.core.logger import get_logger
from devmind.domain.entities.document_chunk import DocumentChunk
from devmind.domain.exceptions import StorageError
from devmind.domain.repositories.chunk_repository import ChunkRepository
from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.infrastructure.persistence.database import SqliteDatabase
from devmind.infrastructure.persistence.mappers import (
    JOINED_DOCUMENT_COLUMNS,
    path_key,
    to_document_chunk,
    to_document_chunks,
)

__all__ = ["SqliteChunkRepository"]

_logger = get_logger(__name__)

_CHUNK_COLUMNS: Final[str] = "c.chunk_id, c.chunk_index, c.content, c.start_offset, c.end_offset"
_SELECT_CHUNKS: Final[str] = f"""
    SELECT {_CHUNK_COLUMNS}, {JOINED_DOCUMENT_COLUMNS}
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
"""
_INSERT: Final[str] = """
    INSERT INTO chunks (chunk_id, document_id, chunk_index, content, start_offset, end_offset)
    VALUES (?, ?, ?, ?, ?, ?)
"""
# A chunk is pending while no embedding from the requested model exists
# for it, which makes an interrupted run resumable and a model change
# self-invalidating.
_PENDING_SOURCE: Final[str] = """
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    LEFT JOIN embeddings e ON e.chunk_id = c.chunk_id AND e.model = ?
    WHERE e.chunk_id IS NULL
"""


class SqliteChunkRepository(ChunkRepository):
    """Stores document chunks in the SQLite knowledge base."""

    def __init__(self, database: SqliteDatabase) -> None:
        """Initialise the repository.

        Args:
            database: Gateway to the knowledge base.
        """
        self._database = database

    def replace_for_document(self, source_path: Path, chunks: Sequence[DocumentChunk]) -> None:
        """Make the stored chunks of a document exactly ``chunks``.

        The removal of the previous chunks and the insertion of the new
        ones share one transaction, so a failure never leaves the
        document half indexed.

        Args:
            source_path: Absolute path of the document. It must already
                be stored.
            chunks: The chunks to store, in reading order.

        Raises:
            StorageError: If the document is unknown, if a chunk belongs
                to a different document, or if the write fails.
        """
        key = path_key(source_path)
        self._assert_chunks_belong_to(key, chunks)

        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id FROM documents WHERE source_path = ?", (key,)
            ).fetchone()
            if row is None:
                raise StorageError(
                    f"Cannot store chunks for '{source_path}': the document is not indexed."
                )
            document_id = row["id"]
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            connection.executemany(
                _INSERT,
                [
                    (
                        chunk.chunk_id.value,
                        document_id,
                        chunk.index,
                        chunk.content,
                        chunk.start_offset,
                        chunk.end_offset,
                    )
                    for chunk in chunks
                ],
            )
        _logger.debug("Stored %d chunks for '%s'", len(chunks), source_path.name)

    def get(self, chunk_id: ChunkId) -> DocumentChunk | None:
        """Read a single chunk by its identifier.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            The chunk, or ``None`` when the identifier is unknown.

        Raises:
            StorageError: If the chunk cannot be read.
        """
        row = self._database.fetch_one(f"{_SELECT_CHUNKS} WHERE c.chunk_id = ?", (chunk_id.value,))
        return to_document_chunk(row) if row is not None else None

    def get_many(self, chunk_ids: Sequence[ChunkId]) -> tuple[DocumentChunk, ...]:
        """Read several chunks by identifier in a single round trip.

        Args:
            chunk_ids: Identifiers to look up. Duplicates are read once.

        Returns:
            The chunks that still exist, in no particular order.

        Raises:
            StorageError: If the chunks cannot be read.
        """
        if not chunk_ids:
            return ()
        unique_ids = {chunk_id.value for chunk_id in chunk_ids}
        placeholders = ", ".join("?" * len(unique_ids))
        rows = self._database.fetch_all(
            f"{_SELECT_CHUNKS} WHERE c.chunk_id IN ({placeholders})",
            tuple(unique_ids),
        )
        return to_document_chunks(rows)

    def list_for_document(self, source_path: Path) -> tuple[DocumentChunk, ...]:
        """Read every chunk of a document, in reading order.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The chunks of the document.

        Raises:
            StorageError: If the chunks cannot be read.
        """
        rows = self._database.fetch_all(
            f"{_SELECT_CHUNKS} WHERE d.source_path = ? ORDER BY c.chunk_index",
            (path_key(source_path),),
        )
        return to_document_chunks(rows)

    def delete_for_document(self, source_path: Path) -> int:
        """Remove every chunk of a document.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The number of chunks removed.

        Raises:
            StorageError: If the chunks cannot be removed.
        """
        return self._database.execute(
            """
            DELETE FROM chunks
            WHERE document_id IN (SELECT id FROM documents WHERE source_path = ?)
            """,
            (path_key(source_path),),
        )

    def list_pending_embedding(self, model: str, limit: int) -> tuple[DocumentChunk, ...]:
        """Read chunks that have no embedding from ``model`` yet.

        Args:
            model: Identifier of the embedding model.
            limit: Maximum number of chunks to return.

        Returns:
            Chunks awaiting an embedding, grouped by document and in
            reading order.

        Raises:
            StorageError: If the chunks cannot be read.
            ValueError: If ``limit`` is not positive.
        """
        if limit <= 0:
            raise ValueError("Limit must be greater than zero.")
        rows = self._database.fetch_all(
            f"""
            SELECT {_CHUNK_COLUMNS}, {JOINED_DOCUMENT_COLUMNS}
            {_PENDING_SOURCE}
            ORDER BY c.document_id, c.chunk_index
            LIMIT ?
            """,
            (model, limit),
        )
        return to_document_chunks(rows)

    def count_pending_embedding(self, model: str) -> int:
        """Count the chunks that have no embedding from ``model`` yet.

        Args:
            model: Identifier of the embedding model.

        Returns:
            The number of chunks awaiting an embedding.

        Raises:
            StorageError: If the chunks cannot be counted.
        """
        return self._database.count(f"SELECT COUNT(*) AS total {_PENDING_SOURCE}", (model,))

    def count(self) -> int:
        """Return the number of stored chunks.

        Raises:
            StorageError: If the chunks cannot be counted.
        """
        return self._database.count("SELECT COUNT(*) AS total FROM chunks")

    @staticmethod
    def _assert_chunks_belong_to(key: str, chunks: Sequence[DocumentChunk]) -> None:
        """Reject a batch that mixes documents.

        Args:
            key: Stored path of the target document.
            chunks: The chunks about to be written.

        Raises:
            StorageError: If a chunk carries a different source path.
        """
        for chunk in chunks:
            if path_key(chunk.metadata.source_path) != key:
                raise StorageError(
                    f"Chunk '{chunk.chunk_id}' belongs to "
                    f"'{chunk.metadata.source_path}', not to '{key}'."
                )
