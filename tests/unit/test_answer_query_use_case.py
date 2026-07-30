"""Unit tests for grounded answer generation, against a real knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from devmind.application.dto import Prompt
from devmind.application.interfaces import ChatProvider, EmbeddingProvider
from devmind.application.prompt_builder import NO_CONTEXT_ANSWER, PromptBuilder
from devmind.application.use_cases import AnswerQueryUseCase, SearchChunksUseCase
from devmind.core.config import RetrievalConfig
from devmind.domain.exceptions import EmbeddingError, GenerationError
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
)
from tests.factories import make_chunks, make_metadata

MODEL = "all-minilm-l6-v2"


class FixedVectorProvider(EmbeddingProvider):
    """Always embeds a query as the same, test-controlled vector."""

    def __init__(self, vector: tuple[float, ...], model: str = MODEL) -> None:
        self._vector = vector
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(Embedding(model=self._model, vector=self._vector) for _ in texts)


class FakeChatProvider(ChatProvider):
    """A chat model stand-in returning a fixed or computed answer."""

    def __init__(self, answer: str = "Routing matches requests to endpoints.") -> None:
        self._answer = answer
        self.calls: list[Prompt] = []

    @property
    def model(self) -> str:
        return "phi-3.5-mini"

    def complete(self, prompt: Prompt) -> str:
        self.calls.append(prompt)
        return self._answer


class FailingChatProvider(ChatProvider):
    """A chat model stand-in that always fails."""

    @property
    def model(self) -> str:
        return "phi-3.5-mini"

    def complete(self, prompt: Prompt) -> str:
        raise GenerationError("the model went away")


@pytest.fixture
def indexed_chunks(
    database: SqliteDatabase, tmp_path: Path
) -> tuple[SqliteChunkRepository, SqliteEmbeddingRepository]:
    metadata = make_metadata(source_path=tmp_path / "routing.md", title="ASP.NET Core Routing")
    SqliteDocumentRepository(database).save(metadata)
    chunk_repository = SqliteChunkRepository(database)
    stored = make_chunks(metadata, ["Endpoint routing matches requests."])
    chunk_repository.replace_for_document(metadata.source_path, stored)
    embedding_repository = SqliteEmbeddingRepository(database)
    embedding_repository.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    return chunk_repository, embedding_repository


def make_use_case(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    chat: ChatProvider,
    *,
    query_vector: tuple[float, ...] = (1.0, 0.0),
    min_score: float = 0.0,
) -> AnswerQueryUseCase:
    search = SearchChunksUseCase(
        chunks=chunks,
        embeddings=embeddings,
        provider=FixedVectorProvider(query_vector),
        retrieval=RetrievalConfig(top_k=5, min_score=min_score),
    )
    return AnswerQueryUseCase(search=search, chat=chat, prompt_builder=PromptBuilder())


# --------------------------------------------------------------------------- #
# Grounded answers
# --------------------------------------------------------------------------- #
def test_a_matching_query_is_answered_and_cited(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks
    use_case = make_use_case(chunks, embeddings, FakeChatProvider("Routing matches requests."))

    answer = use_case.execute("How does routing work?")

    assert answer.text == "Routing matches requests."
    assert answer.is_grounded is True
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk.content == "Endpoint routing matches requests."


def test_the_prompt_is_built_from_the_retrieved_chunks(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks
    chat = FakeChatProvider()
    use_case = make_use_case(chunks, embeddings, chat)

    use_case.execute("How does routing work?")

    assert len(chat.calls) == 1
    assert "Endpoint routing matches requests." in chat.calls[0].user
    assert "How does routing work?" in chat.calls[0].user


# --------------------------------------------------------------------------- #
# The fixed refusal
# --------------------------------------------------------------------------- #
def test_no_indexed_context_returns_the_fixed_refusal(database: SqliteDatabase) -> None:
    use_case = AnswerQueryUseCase(
        search=SearchChunksUseCase(
            chunks=SqliteChunkRepository(database),
            embeddings=SqliteEmbeddingRepository(database),
            provider=FixedVectorProvider((1.0, 0.0)),
            retrieval=RetrievalConfig(),
        ),
        chat=FakeChatProvider(),
        prompt_builder=PromptBuilder(),
    )

    answer = use_case.execute("Anything at all")

    assert answer.text == NO_CONTEXT_ANSWER
    assert answer.citations == ()
    assert answer.is_grounded is False


def test_the_chat_model_is_never_called_when_there_is_no_context(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks
    chat = FakeChatProvider()
    # An orthogonal query vector scores 0.0 against the only stored chunk,
    # and the threshold excludes it, so retrieval finds nothing.
    use_case = make_use_case(chunks, embeddings, chat, query_vector=(0.0, 1.0), min_score=0.5)

    answer = use_case.execute("Something unrelated")

    assert answer.text == NO_CONTEXT_ANSWER
    assert chat.calls == []


# --------------------------------------------------------------------------- #
# Error propagation
# --------------------------------------------------------------------------- #
def test_a_chat_model_failure_propagates(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks
    use_case = make_use_case(chunks, embeddings, FailingChatProvider())

    with pytest.raises(GenerationError, match="went away"):
        use_case.execute("How does routing work?")


def test_a_blank_query_is_rejected(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks
    use_case = make_use_case(chunks, embeddings, FakeChatProvider())

    with pytest.raises(ValueError, match="must not be blank"):
        use_case.execute("   ")


def test_an_embedding_failure_propagates(
    indexed_chunks: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
) -> None:
    chunks, embeddings = indexed_chunks

    class FailingEmbeddingProvider(FixedVectorProvider):
        def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
            raise EmbeddingError("the model went away")

    search = SearchChunksUseCase(
        chunks=chunks,
        embeddings=embeddings,
        provider=FailingEmbeddingProvider((1.0, 0.0)),
        retrieval=RetrievalConfig(),
    )
    use_case = AnswerQueryUseCase(
        search=search, chat=FakeChatProvider(), prompt_builder=PromptBuilder()
    )

    with pytest.raises(EmbeddingError, match="went away"):
        use_case.execute("How does routing work?")
