"""Unit tests for the Chat Service, against a real knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from devmind.application.dto import Prompt
from devmind.application.interfaces import ChatProvider, EmbeddingProvider
from devmind.application.prompt_builder import NO_CONTEXT_ANSWER, PromptBuilder
from devmind.application.use_cases import AnswerQueryUseCase, SearchChunksUseCase
from devmind.core.config import RetrievalConfig, get_settings
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.chat_service import ChatService, build_chat_service
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
    """A chat model stand-in returning a fixed answer."""

    def __init__(self, answer: str = "Routing matches requests.") -> None:
        self._answer = answer

    @property
    def model(self) -> str:
        return "phi-3.5-mini"

    def complete(self, prompt: Prompt) -> str:
        return self._answer


def make_service(
    database: SqliteDatabase,
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    chat: ChatProvider,
    *,
    query_vector: tuple[float, ...] = (1.0, 0.0),
    min_score: float = 0.0,
) -> ChatService:
    search = SearchChunksUseCase(
        chunks=chunks,
        embeddings=embeddings,
        provider=FixedVectorProvider(query_vector),
        retrieval=RetrievalConfig(top_k=5, min_score=min_score),
    )
    answer_use_case = AnswerQueryUseCase(search=search, chat=chat, prompt_builder=PromptBuilder())
    return ChatService(answer_use_case=answer_use_case, database=database)


@pytest.fixture
def indexed(
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


# --------------------------------------------------------------------------- #
# ask() - the six steps
# --------------------------------------------------------------------------- #
def test_ask_returns_a_grounded_answer_with_its_sources(
    database: SqliteDatabase, indexed: tuple[SqliteChunkRepository, SqliteEmbeddingRepository]
) -> None:
    chunks, embeddings = indexed
    service = make_service(
        database, chunks, embeddings, FakeChatProvider("Routing matches requests.")
    )

    answer = service.ask("How does routing work?")

    assert answer.text == "Routing matches requests."
    assert answer.is_grounded is True
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk.metadata.display_title == "ASP.NET Core Routing"


def test_ask_forwards_top_k_and_min_score(
    database: SqliteDatabase, indexed: tuple[SqliteChunkRepository, SqliteEmbeddingRepository]
) -> None:
    chunks, embeddings = indexed
    service = make_service(database, chunks, embeddings, FakeChatProvider())

    answer = service.ask("How does routing work?", top_k=1, min_score=0.9)

    assert answer.is_grounded is True


def test_ask_on_an_empty_knowledge_base_returns_the_fixed_refusal(
    database: SqliteDatabase,
) -> None:
    service = make_service(
        database,
        SqliteChunkRepository(database),
        SqliteEmbeddingRepository(database),
        FakeChatProvider(),
    )

    answer = service.ask("Anything at all")

    assert answer.text == NO_CONTEXT_ANSWER
    assert answer.citations == ()


# --------------------------------------------------------------------------- #
# Logging the sources
# --------------------------------------------------------------------------- #
def test_ask_logs_the_cited_sources(
    database: SqliteDatabase,
    indexed: tuple[SqliteChunkRepository, SqliteEmbeddingRepository],
    caplog: pytest.LogCaptureFixture,
) -> None:
    chunks, embeddings = indexed
    service = make_service(database, chunks, embeddings, FakeChatProvider())

    with caplog.at_level("INFO", logger="devmind"):
        service.ask("How does routing work?")

    messages = [record.getMessage() for record in caplog.records]
    assert any("ASP.NET Core Routing" in message for message in messages)


def test_ask_does_not_log_sources_for_the_fixed_refusal(
    database: SqliteDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    service = make_service(
        database,
        SqliteChunkRepository(database),
        SqliteEmbeddingRepository(database),
        FakeChatProvider(),
    )

    with caplog.at_level("INFO", logger="devmind"):
        service.ask("Anything at all")

    assert not any("grounded in" in record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def test_close_releases_the_database_connection(
    database: SqliteDatabase, indexed: tuple[SqliteChunkRepository, SqliteEmbeddingRepository]
) -> None:
    chunks, embeddings = indexed
    service = make_service(database, chunks, embeddings, FakeChatProvider())
    database.connect()

    service.close()

    # The gateway transparently reopens on the next use; closing must
    # not leave the database unusable.
    assert database.fetch_one("SELECT 1 AS value") is not None


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
def test_build_chat_service_wires_a_working_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVMIND_DB_PATH", str(tmp_path / "devmind.db"))
    monkeypatch.setenv("DEVMIND_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DEVMIND_DOCUMENTS_DIR", str(tmp_path / "documents"))

    service = build_chat_service(get_settings())
    try:
        assert isinstance(service, ChatService)
        assert (tmp_path / "devmind.db").is_file()
    finally:
        service.close()
