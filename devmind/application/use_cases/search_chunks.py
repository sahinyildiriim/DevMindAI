"""Rank stored chunks against a query by semantic similarity."""

from __future__ import annotations

import heapq
from time import perf_counter

from devmind.application.dto.search_result import SearchResult
from devmind.application.interfaces.embedding_provider import EmbeddingProvider
from devmind.core.config import RetrievalConfig
from devmind.core.logger import get_logger
from devmind.domain.repositories.chunk_repository import ChunkRepository
from devmind.domain.repositories.embedding_repository import EmbeddingRepository
from devmind.domain.similarity import cosine_similarity
from devmind.domain.value_objects.chunk_id import ChunkId

__all__ = ["SearchChunksUseCase"]

_logger = get_logger(__name__)


class SearchChunksUseCase:
    """Finds the chunks most relevant to a natural language query.

    Relevance is brute-force cosine similarity against every stored
    embedding from the provider's model: vectors from another model are
    never compared, since the comparison would be meaningless. There is
    no separate vector index - at the scale of a single curated
    documentation set this is fast enough in plain Python, and it avoids
    a dependency whose only job would be to approximate a computation
    that is already exact and quick without it.
    """

    def __init__(
        self,
        chunks: ChunkRepository,
        embeddings: EmbeddingRepository,
        provider: EmbeddingProvider,
        retrieval: RetrievalConfig,
    ) -> None:
        """Initialise the use case.

        Args:
            chunks: Source of the full text of a matched chunk.
            embeddings: Source of the stored vectors to compare against.
            provider: Service turning the query into a vector, using the
                same model the stored vectors must come from.
            retrieval: Default ranking and filtering parameters.
        """
        self._chunks = chunks
        self._embeddings = embeddings
        self._provider = provider
        self._retrieval = retrieval

    def execute(
        self, query: str, *, top_k: int | None = None, min_score: float | None = None
    ) -> tuple[SearchResult, ...]:
        """Find the chunks most relevant to ``query``.

        Args:
            query: Natural language question or search text.
            top_k: Maximum number of results. Defaults to the configured
                retrieval setting.
            min_score: Minimum confidence a chunk must reach to be
                returned. Defaults to the configured retrieval setting.

        Returns:
            Matches ordered from most to least relevant, each at or
            above ``min_score``. Empty when nothing matches, or when no
            chunk has been embedded with the provider's model yet.

        Raises:
            ValueError: If the query is blank, or if ``top_k`` or
                ``min_score`` are supplied but out of range.
            EmbeddingError: If the query cannot be embedded.
            StorageError: If the knowledge base cannot be read.
        """
        if not query.strip():
            raise ValueError("Query must not be blank.")
        resolved_top_k = self._resolve_top_k(top_k)
        resolved_min_score = self._resolve_min_score(min_score)
        started_at = perf_counter()

        model = self._provider.model
        candidates = self._embeddings.list_all(model)
        if not candidates:
            _logger.info("No embeddings from '%s' are indexed yet; search returns nothing", model)
            return ()

        query_embedding = self._provider.embed([query])[0]
        scored: list[tuple[ChunkId, float]] = []
        for chunk_id, embedding in candidates:
            score = cosine_similarity(query_embedding, embedding)
            if score >= resolved_min_score:
                scored.append((chunk_id, score))

        best = heapq.nlargest(resolved_top_k, scored, key=lambda pair: pair[1])
        results = self._to_results(best)

        _logger.info(
            "Found %d result(s) in %.3fs (top_k=%d, min_score=%.2f)",
            len(results),
            perf_counter() - started_at,
            resolved_top_k,
            resolved_min_score,
        )
        return results

    def _to_results(self, ranked: list[tuple[ChunkId, float]]) -> tuple[SearchResult, ...]:
        """Attach chunk content to ranked identifiers.

        The chunks are fetched in one round trip rather than one query
        per result: `top_k` is small, but a chat request already pays
        for one query to list embedding candidates and one to embed the
        query, and there is no reason to add a query per result on top.

        A chunk absent by the time it is looked up - removed between the
        embedding scan and this step - is skipped rather than treated as
        a failure: a single stale reference should not sink an entire
        search.

        Args:
            ranked: Chunk identifiers and their score, best first.

        Returns:
            The matches whose chunk could still be read, in the given,
            best-first order.
        """
        chunks_by_id = {
            chunk.chunk_id: chunk
            for chunk in self._chunks.get_many([chunk_id for chunk_id, _ in ranked])
        }

        results: list[SearchResult] = []
        for chunk_id, score in ranked:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                _logger.warning(
                    "Chunk '%s' was removed while ranking search results; skipping it", chunk_id
                )
                continue
            results.append(SearchResult(chunk=chunk, score=score))
        return tuple(results)

    def _resolve_top_k(self, top_k: int | None) -> int:
        """Validate and default the requested result limit.

        Args:
            top_k: Caller supplied override, or ``None``.

        Returns:
            The limit to apply.

        Raises:
            ValueError: If the resolved limit is not positive.
        """
        resolved = top_k if top_k is not None else self._retrieval.top_k
        if resolved <= 0:
            raise ValueError("top_k must be greater than zero.")
        return resolved

    def _resolve_min_score(self, min_score: float | None) -> float:
        """Validate and default the requested confidence threshold.

        Args:
            min_score: Caller supplied override, or ``None``.

        Returns:
            The threshold to apply.

        Raises:
            ValueError: If the resolved threshold is out of range.
        """
        resolved = min_score if min_score is not None else self._retrieval.min_score
        if not 0.0 <= resolved <= 1.0:
            raise ValueError("min_score must be between 0.0 and 1.0.")
        return resolved
