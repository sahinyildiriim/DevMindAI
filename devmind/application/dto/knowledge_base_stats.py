"""A snapshot of the knowledge base's size and embedding status."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["KnowledgeBaseStats"]


@dataclass(frozen=True, slots=True)
class KnowledgeBaseStats:
    """Counts and embedding status of the knowledge base.

    Attributes:
        document_count: Number of indexed documents.
        chunk_count: Number of stored chunks.
        pending_embedding_count: Number of chunks that do not yet have
            an embedding from ``configured_embedding_model``.
        configured_embedding_model: The embedding model this
            installation is currently configured to use.
        indexed_embedding_model: The model the stored embeddings were
            produced with, or ``None`` if nothing has been embedded yet.
    """

    document_count: int
    chunk_count: int
    pending_embedding_count: int
    configured_embedding_model: str
    indexed_embedding_model: str | None

    @property
    def embedded_count(self) -> int:
        """Chunks that already have an embedding from the configured model."""
        return self.chunk_count - self.pending_embedding_count

    @property
    def is_embedding_model_current(self) -> bool:
        """Whether the stored embeddings match the configured model.

        ``True`` when nothing has been embedded yet: there is no stale
        model to warn about, only work still to be done.
        """
        return (
            self.indexed_embedding_model is None
            or self.indexed_embedding_model == self.configured_embedding_model
        )
