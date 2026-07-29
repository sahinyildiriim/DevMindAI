"""Persistence contract for document chunks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from devmind.domain.entities.document_chunk import DocumentChunk
from devmind.domain.value_objects.chunk_id import ChunkId

__all__ = ["ChunkRepository"]


class ChunkRepository(ABC):
    """Stores the chunks a document was split into."""

    @abstractmethod
    def replace_for_document(self, source_path: Path, chunks: Sequence[DocumentChunk]) -> None:
        """Make the stored chunks of a document exactly ``chunks``.

        Re-indexing a document always replaces its chunks as a whole:
        chunk identifiers change with the content, so a partial update
        would leave stale chunks behind.

        Args:
            source_path: Absolute path of the document the chunks belong
                to. The document must already be stored.
            chunks: The chunks to store, in reading order. An empty
                sequence removes every chunk of the document.

        Raises:
            StorageError: If the document is unknown, if a chunk belongs
                to a different document, or if the write fails.
        """

    @abstractmethod
    def get(self, chunk_id: ChunkId) -> DocumentChunk | None:
        """Read a single chunk by its identifier.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            The chunk with the metadata of its document, or ``None``
            when the identifier is unknown.

        Raises:
            StorageError: If the chunk cannot be read.
        """

    @abstractmethod
    def list_for_document(self, source_path: Path) -> tuple[DocumentChunk, ...]:
        """Read every chunk of a document, in reading order.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The chunks of the document, empty when the path is unknown.

        Raises:
            StorageError: If the chunks cannot be read.
        """

    @abstractmethod
    def delete_for_document(self, source_path: Path) -> int:
        """Remove every chunk of a document.

        Args:
            source_path: Absolute path of the document.

        Returns:
            The number of chunks removed.

        Raises:
            StorageError: If the chunks cannot be removed.
        """

    @abstractmethod
    def list_pending_embedding(self, model: str, limit: int) -> tuple[DocumentChunk, ...]:
        """Read chunks that have no embedding from ``model`` yet.

        Pending work is defined by the absence of an embedding, so a run
        that stops halfway simply resumes where it left off, and
        switching to another model marks every chunk pending again.

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

    @abstractmethod
    def count_pending_embedding(self, model: str) -> int:
        """Count the chunks that have no embedding from ``model`` yet.

        Args:
            model: Identifier of the embedding model.

        Returns:
            The number of chunks awaiting an embedding.

        Raises:
            StorageError: If the chunks cannot be counted.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the number of stored chunks.

        Raises:
            StorageError: If the chunks cannot be counted.
        """
