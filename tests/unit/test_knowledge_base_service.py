"""Unit tests for the Knowledge Base Service, against a real database."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from devmind.application.interfaces import EmbeddingProvider
from devmind.application.use_cases import (
    EmbedChunksUseCase,
    GetKnowledgeBaseStatsUseCase,
    IndexDocumentUseCase,
)
from devmind.core.config import DocumentConfig, RetrievalConfig, get_settings
from devmind.domain.exceptions import DocumentNotFoundError
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.chunking import build_chunker
from devmind.infrastructure.knowledge_base_service import (
    KnowledgeBaseService,
    build_knowledge_base_service,
)
from devmind.infrastructure.parsers import build_parser_registry
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
    SqliteMetadataRepository,
)

MODEL = "all-minilm-l6-v2"


class FixedVectorProvider(EmbeddingProvider):
    """Always embeds text as the same, test-controlled vector."""

    def __init__(self, vector: tuple[float, ...] = (1.0, 0.0), model: str = MODEL) -> None:
        self._vector = vector
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(Embedding(model=self._model, vector=self._vector) for _ in texts)


def make_service(database: SqliteDatabase, provider: EmbeddingProvider) -> KnowledgeBaseService:
    documents = SqliteDocumentRepository(database)
    chunks = SqliteChunkRepository(database)
    index_document = IndexDocumentUseCase(
        parsers=build_parser_registry(DocumentConfig()),
        chunker=build_chunker(RetrievalConfig(chunk_size=1000, chunk_overlap=100)),
        documents=documents,
        chunks=chunks,
    )
    embed_chunks = EmbedChunksUseCase(
        chunks=chunks,
        embeddings=SqliteEmbeddingRepository(database),
        metadata=SqliteMetadataRepository(database),
        provider=provider,
        batch_size=8,
    )
    get_stats = GetKnowledgeBaseStatsUseCase(
        documents=documents,
        chunks=chunks,
        metadata=SqliteMetadataRepository(database),
        configured_embedding_model=provider.model,
    )
    return KnowledgeBaseService(
        index_document=index_document,
        embed_chunks=embed_chunks,
        get_stats=get_stats,
        documents=documents,
        database=database,
    )


def test_index_document_stores_a_new_document(database: SqliteDatabase, tmp_path: Path) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    service = make_service(database, FixedVectorProvider())

    result = service.index_document(source)

    assert result.was_skipped is False
    assert result.chunks_indexed == 1


def test_index_document_propagates_parser_errors(database: SqliteDatabase, tmp_path: Path) -> None:
    service = make_service(database, FixedVectorProvider())

    with pytest.raises(DocumentNotFoundError):
        service.index_document(tmp_path / "absent.md")


def test_embed_pending_embeds_newly_indexed_chunks(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    service = make_service(database, FixedVectorProvider())
    service.index_document(source)

    run = service.embed_pending()

    assert run.embedded == 1
    assert run.model == MODEL


def test_get_stats_reflects_indexing_and_embedding(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    service = make_service(database, FixedVectorProvider())
    service.index_document(source)
    service.embed_pending()

    stats = service.get_stats()

    assert stats.document_count == 1
    assert stats.chunk_count == 1
    assert stats.embedded_count == 1
    assert stats.is_embedding_model_current is True


def test_list_documents_returns_what_was_indexed(database: SqliteDatabase, tmp_path: Path) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    service = make_service(database, FixedVectorProvider())
    service.index_document(source)

    documents = service.list_documents()

    assert len(documents) == 1
    assert documents[0].file_name == "routing.md"


def test_close_releases_the_database_connection(database: SqliteDatabase) -> None:
    service = make_service(database, FixedVectorProvider())
    database.connect()

    service.close()

    assert database.fetch_one("SELECT 1 AS value") is not None


def test_build_knowledge_base_service_wires_a_working_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVMIND_DB_PATH", str(tmp_path / "devmind.db"))
    monkeypatch.setenv("DEVMIND_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DEVMIND_DOCUMENTS_DIR", str(tmp_path / "documents"))

    service = build_knowledge_base_service(get_settings())
    try:
        assert isinstance(service, KnowledgeBaseService)
        stats = service.get_stats()
        assert stats.document_count == 0
    finally:
        service.close()
