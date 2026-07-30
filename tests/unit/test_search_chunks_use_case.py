"""Unit tests for semantic search, against a real knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from devmind.application.interfaces import EmbeddingProvider
from devmind.application.use_cases import SearchChunksUseCase
from devmind.core.config import RetrievalConfig
from devmind.domain.entities import DocumentChunk
from devmind.domain.exceptions import EmbeddingError
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
    SqliteEmbeddingRepository,
)
from tests.factories import make_chunks, make_metadata

MODEL = "all-minilm-l6-v2"

Indexed = tuple[SqliteChunkRepository, SqliteEmbeddingRepository, tuple[DocumentChunk, ...]]


class FixedVectorProvider(EmbeddingProvider):
    """Always embeds a query as the same, test-controlled vector."""

    def __init__(self, vector: tuple[float, ...], model: str = MODEL) -> None:
        self._vector = vector
        self._model = model
        self.calls: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        self.calls.extend(texts)
        return tuple(Embedding(model=self._model, vector=self._vector) for _ in texts)


@pytest.fixture
def indexed(database: SqliteDatabase, tmp_path: Path) -> Indexed:
    metadata = make_metadata(source_path=tmp_path / "routing.md")
    SqliteDocumentRepository(database).save(metadata)
    chunk_repository = SqliteChunkRepository(database)
    stored = make_chunks(
        metadata,
        ["Matches exactly.", "Best partial match.", "Somewhat related.", "Points elsewhere."],
    )
    chunk_repository.replace_for_document(metadata.source_path, stored)
    return chunk_repository, SqliteEmbeddingRepository(database), stored


def make_use_case(
    indexed: Indexed,
    provider: EmbeddingProvider,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
) -> SearchChunksUseCase:
    chunks, embeddings, _ = indexed
    return SearchChunksUseCase(
        chunks=chunks,
        embeddings=embeddings,
        provider=provider,
        retrieval=RetrievalConfig(top_k=top_k, min_score=min_score),
    )


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def test_results_are_ranked_from_most_to_least_relevant(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    embeddings.save(stored[1].chunk_id, Embedding(model=MODEL, vector=(0.8, 0.6)))
    embeddings.save(stored[2].chunk_id, Embedding(model=MODEL, vector=(0.6, 0.8)))
    embeddings.save(stored[3].chunk_id, Embedding(model=MODEL, vector=(0.0, 1.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.0)

    results = use_case.execute("routing basics")

    assert [result.chunk.chunk_id for result in results] == [
        stored[0].chunk_id,
        stored[1].chunk_id,
        stored[2].chunk_id,
        stored[3].chunk_id,
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[-1].score == pytest.approx(0.0)


def test_a_perfect_match_scores_full_confidence(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(0.4, 0.3)))
    use_case = make_use_case(indexed, FixedVectorProvider((0.4, 0.3)), top_k=10, min_score=0.0)

    results = use_case.execute("routing basics")

    assert results[0].score == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Top-K and confidence filtering
# --------------------------------------------------------------------------- #
def test_top_k_limits_the_number_of_results(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    embeddings.save(stored[1].chunk_id, Embedding(model=MODEL, vector=(0.8, 0.6)))
    embeddings.save(stored[2].chunk_id, Embedding(model=MODEL, vector=(0.6, 0.8)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=2, min_score=0.0)

    results = use_case.execute("routing basics")

    assert [result.chunk.chunk_id for result in results] == [stored[0].chunk_id, stored[1].chunk_id]


def test_min_score_filters_out_weak_matches(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    embeddings.save(stored[1].chunk_id, Embedding(model=MODEL, vector=(0.0, 1.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.5)

    results = use_case.execute("routing basics")

    assert len(results) == 1
    assert results[0].chunk.chunk_id == stored[0].chunk_id


def test_a_top_k_override_replaces_the_configured_default(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    for index in range(4):
        embeddings.save(stored[index].chunk_id, Embedding(model=MODEL, vector=(1.0, float(index))))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.0)

    results = use_case.execute("routing basics", top_k=1)

    assert len(results) == 1


def test_a_min_score_override_replaces_the_configured_default(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    embeddings.save(stored[1].chunk_id, Embedding(model=MODEL, vector=(0.0, 1.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.0)

    results = use_case.execute("routing basics", min_score=0.9)

    assert len(results) == 1


# --------------------------------------------------------------------------- #
# Empty and mismatched state
# --------------------------------------------------------------------------- #
def test_an_empty_knowledge_base_returns_nothing(database: SqliteDatabase) -> None:
    use_case = SearchChunksUseCase(
        chunks=SqliteChunkRepository(database),
        embeddings=SqliteEmbeddingRepository(database),
        provider=FixedVectorProvider((1.0, 0.0)),
        retrieval=RetrievalConfig(),
    )

    assert use_case.execute("anything") == ()


def test_embeddings_from_another_model_are_ignored(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model="an-older-model", vector=(1.0, 0.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.0)

    assert use_case.execute("routing basics") == ()


def test_a_query_that_matches_nothing_returns_empty(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(0.0, 1.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)), top_k=10, min_score=0.5)

    assert use_case.execute("routing basics") == ()


# --------------------------------------------------------------------------- #
# Validation and error propagation
# --------------------------------------------------------------------------- #
def test_blank_query_is_rejected(indexed: Indexed) -> None:
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)))

    with pytest.raises(ValueError, match="must not be blank"):
        use_case.execute("   ")


@pytest.mark.parametrize("top_k", [0, -1])
def test_invalid_top_k_override_is_rejected(indexed: Indexed, top_k: int) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)))

    with pytest.raises(ValueError, match="top_k"):
        use_case.execute("routing basics", top_k=top_k)


@pytest.mark.parametrize("min_score", [-0.1, 1.1])
def test_invalid_min_score_override_is_rejected(indexed: Indexed, min_score: float) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    use_case = make_use_case(indexed, FixedVectorProvider((1.0, 0.0)))

    with pytest.raises(ValueError, match="min_score"):
        use_case.execute("routing basics", min_score=min_score)


def test_the_query_is_embedded_exactly_once(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))
    provider = FixedVectorProvider((1.0, 0.0))
    use_case = make_use_case(indexed, provider)

    use_case.execute("how does routing work")

    assert provider.calls == ["how does routing work"]


def test_a_provider_failure_propagates(indexed: Indexed) -> None:
    _, embeddings, stored = indexed
    embeddings.save(stored[0].chunk_id, Embedding(model=MODEL, vector=(1.0, 0.0)))

    class FailingProvider(FixedVectorProvider):
        def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
            raise EmbeddingError("the model went away")

    use_case = make_use_case(indexed, FailingProvider((1.0, 0.0)))

    with pytest.raises(EmbeddingError, match="went away"):
        use_case.execute("routing basics")
