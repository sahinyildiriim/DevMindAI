"""SQLite implementation of :class:`EmbeddingRepository`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from devmind.core.logger import get_logger
from devmind.domain.exceptions import StorageError
from devmind.domain.repositories.embedding_repository import EmbeddingRepository
from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.domain.value_objects.embedding import Embedding
from devmind.infrastructure.persistence.database import SqliteDatabase
from devmind.infrastructure.persistence.serialization import decode_vector, encode_vector

__all__ = ["SqliteEmbeddingRepository"]

_logger = get_logger(__name__)

_UPSERT: Final[str] = """
    INSERT INTO embeddings (chunk_id, model, dimensions, vector)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (chunk_id) DO UPDATE SET
        model      = excluded.model,
        dimensions = excluded.dimensions,
        vector     = excluded.vector
"""


class SqliteEmbeddingRepository(EmbeddingRepository):
    """Stores chunk embeddings in the SQLite knowledge base."""

    def __init__(self, database: SqliteDatabase) -> None:
        """Initialise the repository.

        Args:
            database: Gateway to the knowledge base.
        """
        self._database = database

    def save(self, chunk_id: ChunkId, embedding: Embedding) -> None:
        """Store the embedding of a chunk, replacing any previous one.

        Args:
            chunk_id: Identifier of the chunk the vector describes.
            embedding: The vector to store.

        Raises:
            StorageError: If the chunk is unknown or the write fails.
        """
        self._database.execute(_UPSERT, _values(chunk_id, embedding))
        _logger.debug(
            "Stored %d-dimensional embedding for chunk '%s'", embedding.dimensions, chunk_id
        )

    def save_many(self, embeddings: Mapping[ChunkId, Embedding]) -> None:
        """Store several embeddings in a single transaction.

        Args:
            embeddings: The vectors to store, keyed by chunk.

        Raises:
            StorageError: If a chunk is unknown or the write fails.
        """
        written = self._database.execute_many(
            _UPSERT, [_values(chunk_id, embedding) for chunk_id, embedding in embeddings.items()]
        )
        _logger.debug("Stored %d embeddings", written)

    def get(self, chunk_id: ChunkId) -> Embedding | None:
        """Read the embedding of a chunk.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            The stored embedding, or ``None`` when the chunk has none.

        Raises:
            StorageError: If the embedding cannot be read or is corrupt.
        """
        row = self._database.fetch_one(
            "SELECT model, dimensions, vector FROM embeddings WHERE chunk_id = ?",
            (chunk_id.value,),
        )
        if row is None:
            return None

        vector = decode_vector(row["vector"])
        if len(vector) != row["dimensions"]:
            raise StorageError(
                f"Stored embedding of chunk '{chunk_id}' declares {row['dimensions']} "
                f"dimensions but holds {len(vector)}."
            )
        return Embedding(model=row["model"], vector=vector)

    def delete(self, chunk_id: ChunkId) -> bool:
        """Remove the embedding of a chunk.

        Args:
            chunk_id: Identifier of the chunk.

        Returns:
            ``True`` when an embedding was removed.

        Raises:
            StorageError: If the embedding cannot be removed.
        """
        removed = self._database.execute(
            "DELETE FROM embeddings WHERE chunk_id = ?", (chunk_id.value,)
        )
        return removed > 0

    def count(self) -> int:
        """Return the number of stored embeddings.

        Raises:
            StorageError: If the embeddings cannot be counted.
        """
        row = self._database.fetch_one("SELECT COUNT(*) AS total FROM embeddings")
        return int(row["total"]) if row is not None else 0


def _values(chunk_id: ChunkId, embedding: Embedding) -> tuple[object, ...]:
    """Flatten an embedding into bind parameters.

    Args:
        chunk_id: Identifier of the chunk the vector describes.
        embedding: The vector to store.

    Returns:
        The values to bind, in column order.
    """
    return (
        chunk_id.value,
        embedding.model,
        embedding.dimensions,
        encode_vector(embedding.vector),
    )
