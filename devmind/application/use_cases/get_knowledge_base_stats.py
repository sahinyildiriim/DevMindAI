"""Summarise the size and embedding status of the knowledge base."""

from __future__ import annotations

from devmind.application.dto.knowledge_base_stats import KnowledgeBaseStats
from devmind.application.use_cases.embed_chunks import EMBEDDING_MODEL_KEY
from devmind.domain.repositories.chunk_repository import ChunkRepository
from devmind.domain.repositories.document_repository import DocumentRepository
from devmind.domain.repositories.metadata_repository import MetadataRepository

__all__ = ["GetKnowledgeBaseStatsUseCase"]


class GetKnowledgeBaseStatsUseCase:
    """Reads the counts and embedding status shown on the Knowledge Base page."""

    def __init__(
        self,
        documents: DocumentRepository,
        chunks: ChunkRepository,
        metadata: MetadataRepository,
        configured_embedding_model: str,
    ) -> None:
        """Initialise the use case.

        Args:
            documents: Source of the document count.
            chunks: Source of the chunk and pending-embedding counts.
            metadata: Source of the model the stored embeddings were
                produced with.
            configured_embedding_model: The embedding model this
                installation is currently configured to use.
        """
        self._documents = documents
        self._chunks = chunks
        self._metadata = metadata
        self._configured_embedding_model = configured_embedding_model

    def execute(self) -> KnowledgeBaseStats:
        """Read a fresh snapshot of the knowledge base.

        Returns:
            The current counts and embedding status.

        Raises:
            StorageError: If the knowledge base cannot be read.
        """
        return KnowledgeBaseStats(
            document_count=self._documents.count(),
            chunk_count=self._chunks.count(),
            pending_embedding_count=self._chunks.count_pending_embedding(
                self._configured_embedding_model
            ),
            configured_embedding_model=self._configured_embedding_model,
            indexed_embedding_model=self._metadata.get(EMBEDDING_MODEL_KEY),
        )
