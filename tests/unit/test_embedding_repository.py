"""Unit tests for the SQLite embedding repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.domain.entities import DocumentChunk
from devmind.domain.exceptions import StorageError
from devmind.domain.value_objects import ChunkId
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
)
from tests.factories import make_chunks, make_embedding, make_metadata

CONTENTS = ("Routing matches requests.", "Middleware runs in order.")


@pytest.fixture
def repository(database: SqliteDatabase) -> SqliteEmbeddingRepository:
    return SqliteEmbeddingRepository(database)


@pytest.fixture
def chunks(database: SqliteDatabase, tmp_path: Path) -> tuple[DocumentChunk, ...]:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    stored = make_chunks(metadata, CONTENTS)
    SqliteChunkRepository(database).replace_for_document(metadata.source_path, stored)
    return stored


def test_an_embedding_is_read_back_unchanged(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    embedding = make_embedding(dimensions=8)

    repository.save(chunks[0].chunk_id, embedding)
    stored = repository.get(chunks[0].chunk_id)

    assert stored is not None
    assert stored.model == embedding.model
    assert stored.dimensions == 8
    assert stored.vector == pytest.approx(embedding.vector, rel=1e-6)


def test_chunks_without_an_embedding_read_as_none(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    assert repository.get(chunks[0].chunk_id) is None


def test_saving_twice_replaces_the_vector(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    repository.save(chunks[0].chunk_id, make_embedding(dimensions=4, model="first"))
    repository.save(chunks[0].chunk_id, make_embedding(dimensions=6, model="second"))

    stored = repository.get(chunks[0].chunk_id)

    assert repository.count() == 1
    assert stored is not None
    assert stored.model == "second"
    assert stored.dimensions == 6


def test_embeddings_of_unknown_chunks_are_refused(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    orphan = ChunkId.for_document(chunks[0].metadata.checksum, 99)

    with pytest.raises(StorageError, match="FOREIGN KEY"):
        repository.save(orphan, make_embedding())


def test_saving_many_embeddings_at_once(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    repository.save_many({chunk.chunk_id: make_embedding() for chunk in chunks})

    assert repository.count() == len(chunks)


def test_saving_an_empty_batch_does_nothing(repository: SqliteEmbeddingRepository) -> None:
    repository.save_many({})

    assert repository.count() == 0


def test_deleting_reports_whether_anything_was_removed(
    repository: SqliteEmbeddingRepository, chunks: tuple[DocumentChunk, ...]
) -> None:
    repository.save(chunks[0].chunk_id, make_embedding())

    assert repository.delete(chunks[0].chunk_id) is True
    assert repository.delete(chunks[0].chunk_id) is False


def test_replacing_the_chunks_removes_their_embeddings(
    repository: SqliteEmbeddingRepository,
    database: SqliteDatabase,
    chunks: tuple[DocumentChunk, ...],
) -> None:
    repository.save_many({chunk.chunk_id: make_embedding() for chunk in chunks})

    SqliteChunkRepository(database).replace_for_document(chunks[0].metadata.source_path, ())

    assert repository.count() == 0


def test_deleting_the_document_removes_its_embeddings(
    repository: SqliteEmbeddingRepository,
    database: SqliteDatabase,
    chunks: tuple[DocumentChunk, ...],
) -> None:
    repository.save_many({chunk.chunk_id: make_embedding() for chunk in chunks})

    SqliteDocumentRepository(database).delete(chunks[0].metadata.source_path)

    assert repository.count() == 0


def test_a_vector_that_lost_components_is_reported(
    repository: SqliteEmbeddingRepository,
    database: SqliteDatabase,
    chunks: tuple[DocumentChunk, ...],
) -> None:
    repository.save(chunks[0].chunk_id, make_embedding(dimensions=4))
    database.execute(
        "UPDATE embeddings SET dimensions = 99 WHERE chunk_id = ?", (chunks[0].chunk_id.value,)
    )

    with pytest.raises(StorageError, match="declares 99 dimensions"):
        repository.get(chunks[0].chunk_id)
