"""Persistence contract for chunk embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.domain.value_objects.embedding import Embedding

__all__ = ["EmbeddingRepository"]


class EmbeddingRepository(ABC):
    """Stores one vector per chunk.

    An embedding belongs to exactly one chunk and disappears with it, so
    the index can never keep a vector that no longer has any text behind
    it.
    """

    @abstractmethod
    def save(self, chunk_id: ChunkId, embedding: Embedding) -> None:
        """Store the embedding of a chunk, replacing any previous one.

        Args:
            chunk_id: Identifier of the chunk the vector describes. The
                chunk must already be stored.
            embedding: The vector to store.

        Raises:
            StorageError: If the chunk is unknown or the write fails.
        """

    @abstractmethod
    def save_many(self, embeddings: Mapping[ChunkId, Embedding]) -> None:
        """Store several embeddings in a single transaction.

        Args:
            embeddings: The vectors to store, keyed by chunk.

        Raises:
            StorageError: If a chunk is unknown or the write fails.
        """

    @abstractmethod
    def get(self, chunk_id: ChunkId) -> Embedding | None:
        """Read the embedding of a chunk.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            The stored embedding, or ``None`` when the chunk has none.

        Raises:
            StorageError: If the embedding cannot be read.
        """

    @abstractmethod
    def delete(self, chunk_id: ChunkId) -> bool:
        """Remove the embedding of a chunk.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            ``True`` when an embedding was removed.

        Raises:
            StorageError: If the embedding cannot be removed.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the number of stored embeddings.

        Raises:
            StorageError: If the embeddings cannot be counted.
        """
