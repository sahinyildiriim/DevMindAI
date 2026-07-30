"""A chunk matched against a query, ranked by relevance."""

from __future__ import annotations

from dataclasses import dataclass

from devmind.domain.entities.document_chunk import DocumentChunk

__all__ = ["SearchResult"]


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One ranked match returned by semantic search.

    Attributes:
        chunk: The matched chunk, carrying its source document metadata
            so the caller can attribute the match without a second
            lookup.
        score: Confidence that the chunk answers the query, in the
            closed interval [0, 1]. See
            :func:`devmind.domain.similarity.cosine_similarity`.
    """

    chunk: DocumentChunk
    score: float
