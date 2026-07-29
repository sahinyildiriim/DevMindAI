"""Unit tests for the embedding run, against a real knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from devmind.application.interfaces import EmbeddingProvider
from devmind.application.use_cases import EMBEDDING_MODEL_KEY, EmbedChunksUseCase
from devmind.domain.exceptions import EmbeddingError
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
    SqliteMetadataRepository,
)
from tests.factories import make_chunks, make_metadata

CHUNK_COUNT = 5


class FakeProvider(EmbeddingProvider):
    """Deterministic stand-in for Foundry Local."""

    def __init__(
        self,
        model: str = "all-minilm-l6-v2",
        *,
        fail_on_call: int | None = None,
        stamp: str | None = None,
    ) -> None:
        self._model = model
        self._stamp = stamp or model
        self._fail_on_call = fail_on_call
        self.calls: list[list[str]] = []

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        self.calls.append(list(texts))
        if self._fail_on_call is not None and len(self.calls) == self._fail_on_call:
            raise EmbeddingError("the model went away")
        return tuple(
            Embedding(model=self._stamp, vector=(float(len(text)), 0.25, 0.5)) for text in texts
        )


@pytest.fixture
def chunks(database: SqliteDatabase, tmp_path: Path) -> SqliteChunkRepository:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    repository = SqliteChunkRepository(database)
    repository.replace_for_document(
        metadata.source_path,
        make_chunks(metadata, [f"Chunk number {index}." for index in range(CHUNK_COUNT)]),
    )
    return repository


@pytest.fixture
def embeddings(database: SqliteDatabase) -> SqliteEmbeddingRepository:
    return SqliteEmbeddingRepository(database)


@pytest.fixture
def metadata_store(database: SqliteDatabase) -> SqliteMetadataRepository:
    return SqliteMetadataRepository(database)


def make_use_case(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
    provider: EmbeddingProvider,
    batch_size: int = 2,
) -> EmbedChunksUseCase:
    return EmbedChunksUseCase(
        chunks=chunks,
        embeddings=embeddings,
        metadata=metadata_store,
        provider=provider,
        batch_size=batch_size,
    )


# --------------------------------------------------------------------------- #
# Storing the vectors
# --------------------------------------------------------------------------- #
def test_every_pending_chunk_is_embedded_and_stored(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    run = make_use_case(chunks, embeddings, metadata_store, FakeProvider()).execute()

    assert run.embedded == CHUNK_COUNT
    assert run.model == "all-minilm-l6-v2"
    assert run.had_work is True
    assert embeddings.count() == CHUNK_COUNT


def test_the_stored_vector_belongs_to_its_own_chunk(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
    tmp_path: Path,
) -> None:
    make_use_case(chunks, embeddings, metadata_store, FakeProvider()).execute()

    for chunk in chunks.list_for_document(tmp_path / "routing.md"):
        stored = embeddings.get(chunk.chunk_id)
        assert stored is not None
        assert stored.vector[0] == pytest.approx(float(len(chunk.content)))


def test_the_model_in_use_is_recorded(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    make_use_case(chunks, embeddings, metadata_store, FakeProvider()).execute()

    assert metadata_store.get(EMBEDDING_MODEL_KEY) == "all-minilm-l6-v2"


# --------------------------------------------------------------------------- #
# Batching and progress
# --------------------------------------------------------------------------- #
def test_work_is_sent_in_batches_of_the_configured_size(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    provider = FakeProvider()

    run = make_use_case(chunks, embeddings, metadata_store, provider, batch_size=2).execute()

    assert [len(call) for call in provider.calls] == [2, 2, 1]
    assert run.batches == 3


def test_a_single_batch_covers_a_small_index(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    provider = FakeProvider()

    run = make_use_case(chunks, embeddings, metadata_store, provider, batch_size=50).execute()

    assert run.batches == 1
    assert len(provider.calls) == 1


def test_progress_is_reported_per_batch(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="devmind"):
        make_use_case(chunks, embeddings, metadata_store, FakeProvider(), batch_size=2).execute()

    progress = [
        record.getMessage() for record in caplog.records if "chunks (" in record.getMessage()
    ]
    assert progress == [
        "Embedded 2/5 chunks (40%)",
        "Embedded 4/5 chunks (80%)",
        "Embedded 5/5 chunks (100%)",
    ]


# --------------------------------------------------------------------------- #
# Resuming and re-running
# --------------------------------------------------------------------------- #
def test_a_second_run_finds_nothing_to_do(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    make_use_case(chunks, embeddings, metadata_store, FakeProvider()).execute()
    provider = FakeProvider()

    run = make_use_case(chunks, embeddings, metadata_store, provider).execute()

    assert run.embedded == 0
    assert run.had_work is False
    assert provider.calls == []
    assert embeddings.count() == CHUNK_COUNT


def test_a_failed_batch_keeps_the_work_already_done(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    failing = FakeProvider(fail_on_call=2)

    with pytest.raises(EmbeddingError, match="went away"):
        make_use_case(chunks, embeddings, metadata_store, failing, batch_size=2).execute()

    assert embeddings.count() == 2


def test_a_later_run_completes_what_a_failure_interrupted(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    with pytest.raises(EmbeddingError):
        make_use_case(
            chunks, embeddings, metadata_store, FakeProvider(fail_on_call=2), batch_size=2
        ).execute()

    run = make_use_case(chunks, embeddings, metadata_store, FakeProvider(), batch_size=2).execute()

    assert run.embedded == CHUNK_COUNT - 2
    assert embeddings.count() == CHUNK_COUNT


def test_switching_the_model_re_embeds_everything(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
    tmp_path: Path,
) -> None:
    make_use_case(chunks, embeddings, metadata_store, FakeProvider("first-model")).execute()

    run = make_use_case(chunks, embeddings, metadata_store, FakeProvider("second-model")).execute()

    assert run.embedded == CHUNK_COUNT
    assert embeddings.count() == CHUNK_COUNT
    stored = embeddings.get(chunks.list_for_document(tmp_path / "routing.md")[0].chunk_id)
    assert stored is not None
    assert stored.model == "second-model"
    assert metadata_store.get(EMBEDDING_MODEL_KEY) == "second-model"


def test_an_empty_knowledge_base_is_not_a_failure(
    database: SqliteDatabase,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    provider = FakeProvider()

    run = make_use_case(
        SqliteChunkRepository(database), embeddings, metadata_store, provider
    ).execute()

    assert run.embedded == 0
    assert run.batches == 0
    assert provider.calls == []


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def test_a_provider_that_mislabels_its_vectors_is_refused(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
) -> None:
    liar = FakeProvider("announced-model", stamp="actual-model")

    with pytest.raises(EmbeddingError, match="announced model 'announced-model'"):
        make_use_case(chunks, embeddings, metadata_store, liar).execute()

    assert embeddings.count() == 0


@pytest.mark.parametrize("batch_size", [0, -1])
def test_an_invalid_batch_size_is_rejected(
    chunks: SqliteChunkRepository,
    embeddings: SqliteEmbeddingRepository,
    metadata_store: SqliteMetadataRepository,
    batch_size: int,
) -> None:
    with pytest.raises(ValueError, match="Batch size"):
        make_use_case(chunks, embeddings, metadata_store, FakeProvider(), batch_size)
