"""Shared fakes and wiring for the integration test suite.

The two composition roots, :class:`ChatService` and
:class:`KnowledgeBaseService`, are built here exactly as
:func:`~devmind.infrastructure.chat_service.build_chat_service` and
:func:`~devmind.infrastructure.knowledge_base_service.build_knowledge_base_service`
build them in production, with one difference: the Foundry Local
adapters are replaced by deterministic fakes, since no test environment
can depend on a locally running model service. Each service still opens
its own connection to the same database file, exactly as it does in
production.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from devmind.application.dto import Prompt
from devmind.application.interfaces import ChatProvider, EmbeddingProvider
from devmind.application.prompt_builder import PromptBuilder
from devmind.application.use_cases import (
    AnswerQueryUseCase,
    EmbedChunksUseCase,
    GetKnowledgeBaseStatsUseCase,
    IndexDocumentUseCase,
    SearchChunksUseCase,
)
from devmind.core.config import DocumentConfig, RetrievalConfig
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.chat_service import ChatService
from devmind.infrastructure.chunking import build_chunker
from devmind.infrastructure.knowledge_base_service import KnowledgeBaseService
from devmind.infrastructure.parsers import build_parser_registry
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
    SqliteMetadataRepository,
)

__all__ = [
    "MODEL",
    "EchoChatProvider",
    "TopicEmbeddingProvider",
    "build_chat_service_for_test",
    "build_knowledge_base_service_for_test",
]

MODEL: Final[str] = "integration-test-embedding-model"

# A small vocabulary of words the fixture documents are written around,
# so genuinely different topics produce genuinely different vectors.
_VOCABULARY: Final[tuple[str, ...]] = (
    "routing",
    "endpoint",
    "middleware",
    "pipeline",
    "dependency",
    "injection",
    "container",
    "service",
    "architecture",
    "layer",
    "domain",
    "clean",
)


class TopicEmbeddingProvider(EmbeddingProvider):
    """Deterministic embeddings reflecting real word overlap between texts.

    A small bag-of-words vector over a fixed vocabulary is not a real
    embedding model, but it is not arbitrary either: two texts that
    share more of these words score higher by cosine similarity, so
    these tests can verify actual ranking behaviour, not just plumbing.
    """

    def __init__(self, model: str = MODEL) -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(self._vectorize(text) for text in texts)

    def _vectorize(self, text: str) -> Embedding:
        lowered = text.lower()
        vector = tuple(float(lowered.count(word)) + 0.01 for word in _VOCABULARY)
        return Embedding(model=self._model, vector=vector)


class EchoChatProvider(ChatProvider):
    """Returns a canned answer, recording every prompt it was given."""

    def __init__(self, answer: str = "Grounded answer.") -> None:
        self._answer = answer
        self.received_prompts: list[Prompt] = []

    @property
    def model(self) -> str:
        return "integration-test-chat-model"

    def complete(self, prompt: Prompt) -> str:
        self.received_prompts.append(prompt)
        return self._answer


def build_knowledge_base_service_for_test(
    db_path: Path, embedding_provider: EmbeddingProvider
) -> KnowledgeBaseService:
    """Wire a :class:`KnowledgeBaseService` against a real SQLite file.

    Args:
        db_path: Location of the knowledge base file.
        embedding_provider: Fake standing in for Foundry Local.

    Returns:
        A fully wired service, ready to index documents.
    """
    database = SqliteDatabase(db_path)
    database.initialize()
    documents = SqliteDocumentRepository(database)
    chunks = SqliteChunkRepository(database)
    metadata = SqliteMetadataRepository(database)

    index_document = IndexDocumentUseCase(
        parsers=build_parser_registry(DocumentConfig(max_file_size_mb=25)),
        chunker=build_chunker(RetrievalConfig(chunk_size=500, chunk_overlap=50)),
        documents=documents,
        chunks=chunks,
    )
    embed_chunks = EmbedChunksUseCase(
        chunks=chunks,
        embeddings=SqliteEmbeddingRepository(database),
        metadata=metadata,
        provider=embedding_provider,
        batch_size=8,
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


def build_chat_service_for_test(
    db_path: Path, embedding_provider: EmbeddingProvider, chat_provider: ChatProvider
) -> ChatService:
    """Wire a :class:`ChatService` against a real SQLite file.

    Opens its own connection to ``db_path`` rather than sharing the one
    :func:`build_knowledge_base_service_for_test` opens, mirroring how
    the two composition roots are independently wired in production.

    Args:
        db_path: Location of the knowledge base file.
        embedding_provider: Fake standing in for Foundry Local's
            embedding model. Must be the same instance (or at least the
            same model identifier) used to index the documents this
            service will search, since search only ever compares
            vectors from one model.
        chat_provider: Fake standing in for Foundry Local's chat model.

    Returns:
        A fully wired service, ready to answer questions.
    """
    database = SqliteDatabase(db_path)
    database.initialize()
    search = SearchChunksUseCase(
        chunks=SqliteChunkRepository(database),
        embeddings=SqliteEmbeddingRepository(database),
        provider=embedding_provider,
        retrieval=RetrievalConfig(top_k=5, min_score=0.0),
    )
    answer_use_case = AnswerQueryUseCase(
        search=search, chat=chat_provider, prompt_builder=PromptBuilder()
    )
    return ChatService(answer_use_case=answer_use_case, database=database)
