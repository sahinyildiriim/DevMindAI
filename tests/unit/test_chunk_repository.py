"""Unit tests for the SQLite chunk repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.domain.exceptions import StorageError
from devmind.domain.value_objects import ChunkId, DocumentMetadata
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
)
from tests.factories import make_chunks, make_embedding, make_metadata

CONTENTS = ("Routing matches requests.", "Middleware runs in order.", "Services are injected.")


@pytest.fixture
def documents(database: SqliteDatabase) -> SqliteDocumentRepository:
    return SqliteDocumentRepository(database)


@pytest.fixture
def repository(database: SqliteDatabase) -> SqliteChunkRepository:
    return SqliteChunkRepository(database)


@pytest.fixture
def stored_document(documents: SqliteDocumentRepository, tmp_path: Path) -> DocumentMetadata:
    metadata = make_metadata(
        source_path=tmp_path / "routing.md", title="Routing", author="Microsoft Learn"
    )
    documents.save(metadata)
    return metadata


def test_chunks_are_read_back_in_reading_order(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)

    repository.replace_for_document(stored_document.source_path, chunks)

    assert repository.list_for_document(stored_document.source_path) == chunks


def test_a_chunk_carries_its_document_metadata(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)

    stored = repository.get(chunks[1].chunk_id)

    assert stored is not None
    assert stored.metadata == stored_document
    assert stored.metadata.title == "Routing"
    assert stored.index == 1
    assert stored.content == CONTENTS[1]


def test_unknown_chunk_identifiers_read_as_none(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    assert repository.get(ChunkId.for_document(stored_document.checksum, 99)) is None


def test_replacing_removes_the_previous_chunks(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    repository.replace_for_document(
        stored_document.source_path, make_chunks(stored_document, CONTENTS)
    )
    replacement = make_chunks(stored_document, ("A single, shorter chunk.",))

    repository.replace_for_document(stored_document.source_path, replacement)

    assert repository.list_for_document(stored_document.source_path) == replacement
    assert repository.count() == 1


def test_replacing_with_nothing_clears_the_document(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    repository.replace_for_document(
        stored_document.source_path, make_chunks(stored_document, CONTENTS)
    )

    repository.replace_for_document(stored_document.source_path, ())

    assert repository.list_for_document(stored_document.source_path) == ()


def test_chunks_of_an_unindexed_document_are_refused(
    repository: SqliteChunkRepository, tmp_path: Path
) -> None:
    metadata = make_metadata(source_path=tmp_path / "unknown.md")

    with pytest.raises(StorageError, match="not indexed"):
        repository.replace_for_document(metadata.source_path, make_chunks(metadata, CONTENTS))


def test_a_batch_may_not_mix_documents(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata, tmp_path: Path
) -> None:
    foreign = make_chunks(make_metadata(source_path=tmp_path / "other.md"), ("Foreign chunk.",))

    with pytest.raises(StorageError, match="belongs to"):
        repository.replace_for_document(stored_document.source_path, foreign)


def test_nothing_is_written_when_a_batch_is_refused(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata, tmp_path: Path
) -> None:
    valid = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, valid)
    foreign = make_chunks(make_metadata(source_path=tmp_path / "other.md"), ("Foreign chunk.",))

    with pytest.raises(StorageError):
        repository.replace_for_document(stored_document.source_path, [*valid, *foreign])

    assert repository.list_for_document(stored_document.source_path) == valid


def test_deleting_the_chunks_of_a_document(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    repository.replace_for_document(
        stored_document.source_path, make_chunks(stored_document, CONTENTS)
    )

    assert repository.delete_for_document(stored_document.source_path) == len(CONTENTS)
    assert repository.delete_for_document(stored_document.source_path) == 0


def test_deleting_the_document_removes_its_chunks(
    repository: SqliteChunkRepository,
    documents: SqliteDocumentRepository,
    stored_document: DocumentMetadata,
) -> None:
    repository.replace_for_document(
        stored_document.source_path, make_chunks(stored_document, CONTENTS)
    )

    documents.delete(stored_document.source_path)

    assert repository.count() == 0


def test_chunks_of_an_unknown_document_read_as_empty(
    repository: SqliteChunkRepository, tmp_path: Path
) -> None:
    assert repository.list_for_document(tmp_path / "absent.md") == ()
    assert repository.count() == 0


# --------------------------------------------------------------------------- #
# get_many()
# --------------------------------------------------------------------------- #
def test_get_many_reads_every_requested_chunk(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)

    found = repository.get_many([chunks[0].chunk_id, chunks[2].chunk_id])

    assert {chunk.chunk_id for chunk in found} == {chunks[0].chunk_id, chunks[2].chunk_id}


def test_get_many_shares_metadata_across_documents(
    repository: SqliteChunkRepository, documents: SqliteDocumentRepository, tmp_path: Path
) -> None:
    first_document = make_metadata(source_path=tmp_path / "first.md", title="First")
    second_document = make_metadata(
        source_path=tmp_path / "second.md", title="Second", checksum="b" * 64
    )
    documents.save(first_document)
    documents.save(second_document)
    first_chunks = make_chunks(first_document, ["From the first document."])
    second_chunks = make_chunks(second_document, ["From the second document."])
    repository.replace_for_document(first_document.source_path, first_chunks)
    repository.replace_for_document(second_document.source_path, second_chunks)

    found = {
        chunk.chunk_id: chunk
        for chunk in repository.get_many([first_chunks[0].chunk_id, second_chunks[0].chunk_id])
    }

    assert found[first_chunks[0].chunk_id].metadata.title == "First"
    assert found[second_chunks[0].chunk_id].metadata.title == "Second"


def test_get_many_omits_unknown_identifiers(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)
    unknown = ChunkId.for_document("f" * 64, 0)

    found = repository.get_many([chunks[0].chunk_id, unknown])

    assert {chunk.chunk_id for chunk in found} == {chunks[0].chunk_id}


def test_get_many_deduplicates_repeated_identifiers(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)

    found = repository.get_many([chunks[0].chunk_id, chunks[0].chunk_id])

    assert len(found) == 1


def test_get_many_with_no_identifiers_makes_no_query(
    repository: SqliteChunkRepository,
) -> None:
    assert repository.get_many([]) == ()


# --------------------------------------------------------------------------- #
# Pending embeddings
# --------------------------------------------------------------------------- #
def test_every_chunk_is_pending_before_anything_is_embedded(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)

    assert repository.count_pending_embedding("all-minilm-l6-v2") == len(CONTENTS)
    assert repository.list_pending_embedding("all-minilm-l6-v2", 10) == chunks


def test_an_embedded_chunk_stops_being_pending(
    repository: SqliteChunkRepository,
    database: SqliteDatabase,
    stored_document: DocumentMetadata,
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)
    SqliteEmbeddingRepository(database).save(chunks[0].chunk_id, make_embedding())

    pending = repository.list_pending_embedding("all-minilm-l6-v2", 10)

    assert repository.count_pending_embedding("all-minilm-l6-v2") == len(CONTENTS) - 1
    assert chunks[0] not in pending


def test_a_vector_from_another_model_leaves_the_chunk_pending(
    repository: SqliteChunkRepository,
    database: SqliteDatabase,
    stored_document: DocumentMetadata,
) -> None:
    chunks = make_chunks(stored_document, CONTENTS)
    repository.replace_for_document(stored_document.source_path, chunks)
    SqliteEmbeddingRepository(database).save(
        chunks[0].chunk_id, make_embedding(model="an-older-model")
    )

    assert repository.count_pending_embedding("all-minilm-l6-v2") == len(CONTENTS)


def test_pending_chunks_respect_the_limit(
    repository: SqliteChunkRepository, stored_document: DocumentMetadata
) -> None:
    repository.replace_for_document(
        stored_document.source_path, make_chunks(stored_document, CONTENTS)
    )

    assert len(repository.list_pending_embedding("all-minilm-l6-v2", 2)) == 2


@pytest.mark.parametrize("limit", [0, -1])
def test_a_non_positive_limit_is_rejected(repository: SqliteChunkRepository, limit: int) -> None:
    with pytest.raises(ValueError, match="Limit"):
        repository.list_pending_embedding("all-minilm-l6-v2", limit)
