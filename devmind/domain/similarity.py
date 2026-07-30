"""Pure vector comparison used to rank chunks against a query."""

from __future__ import annotations

import math

from devmind.domain.value_objects.embedding import Embedding

__all__ = ["cosine_similarity"]


def cosine_similarity(a: Embedding, b: Embedding) -> float:
    """Measure how closely two embeddings point in the same direction.

    The result doubles as a confidence score: retrieval ranks and
    filters candidates by this single value.

    Args:
        a: First embedding.
        b: Second embedding, compared against ``a``.

    Returns:
        A value in the closed interval [0, 1]. Cosine similarity is
        mathematically defined on [-1, 1]; a negative value means the
        vectors point in opposing directions and carries no useful
        signal for ranking relevant text, so it is floored at 0, and the
        upper bound is clamped to absorb floating point drift when
        comparing a vector to itself. A zero-magnitude vector - never
        produced by a real embedding model, but not excluded by
        :class:`Embedding` either - similarly yields 0: it points in no
        direction, so it cannot be said to align with anything.

    Raises:
        ValueError: If the embeddings do not share the same number of
            dimensions.
    """
    if a.dimensions != b.dimensions:
        raise ValueError(
            f"Cannot compare embeddings of different dimensions: {a.dimensions} vs {b.dimensions}."
        )

    dot_product = sum(x * y for x, y in zip(a.vector, b.vector, strict=True))
    magnitude_a = math.sqrt(sum(x * x for x in a.vector))
    magnitude_b = math.sqrt(sum(y * y for y in b.vector))
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)
    return max(0.0, min(1.0, similarity))
