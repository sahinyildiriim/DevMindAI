"""Unit tests for knowledge base statistics, against a real database."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.application.use_cases import EMBEDDING_MODEL_KEY, GetKnowledgeBaseStatsUseCase
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
    SqliteMetadataRepository,
)
from tests.factories import make_chunks, make_embedding, make_metadata

MODEL = "all-minilm-l6-v2"


def make_use_case(database: SqliteDatabase, *, model: str = MODEL) -> GetKnowledgeBaseStatsUseCase:
    return GetKnowledgeBaseStatsUseCase(
        documents=SqliteDocumentRepository(database),
        chunks=SqliteChunkRepository(database),
        metadata=SqliteMetadataRepository(database),
        configured_embedding_model=model,
    )


def test_an_empty_knowledge_base_reports_all_zeros(database: SqliteDatabase) -> None:
    stats = make_use_case(database).execute()

    assert stats.document_count == 0
    assert stats.chunk_count == 0
    assert stats.pending_embedding_count == 0
    assert stats.embedded_count == 0
    assert stats.indexed_embedding_model is None
    assert stats.is_embedding_model_current is True


def test_counts_reflect_indexed_documents_and_chunks(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    SqliteChunkRepository(database).replace_for_document(
        metadata.source_path,
        make_chunks(metadata, ["First chunk.", "Second chunk.", "Third chunk."]),
    )

    stats = make_use_case(database).execute()

    assert stats.document_count == 1
    assert stats.chunk_count == 3
    assert stats.pending_embedding_count == 3
    assert stats.embedded_count == 0


def test_embedded_chunks_from_the_configured_model_reduce_the_pending_count(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    chunks = make_chunks(metadata, ["First chunk.", "Second chunk."])
    SqliteChunkRepository(database).replace_for_document(metadata.source_path, chunks)
    embeddings = SqliteEmbeddingRepository(database)
    embeddings.save(chunks[0].chunk_id, make_embedding(model=MODEL))
    SqliteMetadataRepository(database).put(EMBEDDING_MODEL_KEY, MODEL)

    stats = make_use_case(database).execute()

    assert stats.chunk_count == 2
    assert stats.embedded_count == 1
    assert stats.pending_embedding_count == 1
    assert stats.indexed_embedding_model == MODEL
    assert stats.is_embedding_model_current is True


def test_embeddings_from_a_stale_model_are_reported_as_out_of_date(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    chunks = make_chunks(metadata, ["First chunk."])
    SqliteChunkRepository(database).replace_for_document(metadata.source_path, chunks)
    SqliteEmbeddingRepository(database).save(
        chunks[0].chunk_id, make_embedding(model="an-older-model")
    )
    SqliteMetadataRepository(database).put(EMBEDDING_MODEL_KEY, "an-older-model")

    stats = make_use_case(database, model="all-minilm-l6-v2").execute()

    # The stale embedding does not count toward the configured model.
    assert stats.pending_embedding_count == 1
    assert stats.embedded_count == 0
    assert stats.indexed_embedding_model == "an-older-model"
    assert stats.is_embedding_model_current is False


@pytest.mark.parametrize("model", [MODEL, "a-different-model"])
def test_the_configured_model_is_echoed_back(database: SqliteDatabase, model: str) -> None:
    stats = make_use_case(database, model=model).execute()

    assert stats.configured_embedding_model == model
