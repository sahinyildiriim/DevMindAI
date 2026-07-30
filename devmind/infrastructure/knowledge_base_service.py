"""The single entry point for managing the knowledge base's contents.

This is the composition root for indexing and inspection: it wires the
concrete SQLite repositories, the parser registry and the chunker
behind :class:`IndexDocumentUseCase`, :class:`EmbedChunksUseCase` and
:class:`GetKnowledgeBaseStatsUseCase`, so a caller - the Streamlit UI, a
CLI, or a test - never needs to construct any of them itself. It owns
its own knowledge base connection, independent of the one
:class:`~devmind.infrastructure.chat_service.ChatService` owns: SQLite's
write-ahead log lets both coexist safely, which is a simpler design than
sharing one connection and its lifecycle between two otherwise
unrelated services.
"""

from __future__ import annotations

from pathlib import Path

from devmind.application.dto.embedding_run import EmbeddingRun
from devmind.application.dto.indexing_result import IndexingResult
from devmind.application.dto.knowledge_base_stats import KnowledgeBaseStats
from devmind.application.use_cases.embed_chunks import EmbedChunksUseCase
from devmind.application.use_cases.get_knowledge_base_stats import GetKnowledgeBaseStatsUseCase
from devmind.application.use_cases.index_document import IndexDocumentUseCase
from devmind.core.config import Settings, get_settings
from devmind.domain.value_objects.document_metadata import DocumentMetadata
from devmind.infrastructure.chunking import build_chunker
from devmind.infrastructure.embeddings import build_embedding_provider
from devmind.infrastructure.parsers import build_parser_registry
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
    SqliteMetadataRepository,
    build_database,
)

__all__ = ["KnowledgeBaseService", "build_knowledge_base_service"]


class KnowledgeBaseService:
    """Indexes documents and reports on the knowledge base's contents."""

    def __init__(
        self,
        index_document: IndexDocumentUseCase,
        embed_chunks: EmbedChunksUseCase,
        get_stats: GetKnowledgeBaseStatsUseCase,
        documents: SqliteDocumentRepository,
        database: SqliteDatabase,
    ) -> None:
        """Initialise the service.

        Args:
            index_document: Parses, chunks and stores a single document.
            embed_chunks: Embeds every pending chunk in one run.
            get_stats: Reads the knowledge base's counts and embedding
                status.
            documents: Source of the indexed document list.
            database: Knowledge base connection this service owns and
                is responsible for closing.
        """
        self._index_document = index_document
        self._embed_chunks = embed_chunks
        self._get_stats = get_stats
        self._documents = documents
        self._database = database

    def index_document(self, source_path: Path) -> IndexingResult:
        """Parse, chunk and store a single document.

        Args:
            source_path: Path of the file to index.

        Returns:
            What indexing accomplished.

        Raises:
            DocumentError: If the file cannot be parsed.
            StorageError: If the knowledge base cannot be read or
                written.
        """
        return self._index_document.execute(source_path)

    def embed_pending(self) -> EmbeddingRun:
        """Embed every chunk that does not have one yet.

        Returns:
            What the run accomplished.

        Raises:
            EmbeddingError: If the embedding model fails.
            StorageError: If the knowledge base cannot be read or
                written.
        """
        return self._embed_chunks.execute()

    def get_stats(self) -> KnowledgeBaseStats:
        """Read a fresh snapshot of the knowledge base.

        Raises:
            StorageError: If the knowledge base cannot be read.
        """
        return self._get_stats.execute()

    def list_documents(self) -> tuple[DocumentMetadata, ...]:
        """List every indexed document, ordered by source path.

        Raises:
            StorageError: If the documents cannot be read.
        """
        return self._documents.list_all()

    def close(self) -> None:
        """Release the knowledge base connection held by this service."""
        self._database.close()


def build_knowledge_base_service(settings: Settings | None = None) -> KnowledgeBaseService:
    """Wire the indexing pipeline from the active configuration.

    Args:
        settings: Application settings to apply. Defaults to the active
            settings.

    Returns:
        A service ready to index documents and report on them. Call
        :meth:`KnowledgeBaseService.close` once it is no longer needed.

    Raises:
        StorageError: If the knowledge base cannot be opened.
    """
    resolved = settings if settings is not None else get_settings()
    database = build_database(resolved.database)
    documents = SqliteDocumentRepository(database)
    chunks = SqliteChunkRepository(database)
    metadata = SqliteMetadataRepository(database)
    embedding_provider = build_embedding_provider(resolved.foundry)

    index_document = IndexDocumentUseCase(
        parsers=build_parser_registry(resolved.documents),
        chunker=build_chunker(resolved.retrieval),
        documents=documents,
        chunks=chunks,
    )
    embed_chunks = EmbedChunksUseCase(
        chunks=chunks,
        embeddings=SqliteEmbeddingRepository(database),
        metadata=metadata,
        provider=embedding_provider,
        batch_size=resolved.foundry.embedding_batch_size,
    )
    get_stats = GetKnowledgeBaseStatsUseCase(
        documents=documents,
        chunks=chunks,
        metadata=metadata,
        configured_embedding_model=embedding_provider.model,
    )
    return KnowledgeBaseService(
        index_document=index_document,
        embed_chunks=embed_chunks,
        get_stats=get_stats,
        documents=documents,
        database=database,
    )
