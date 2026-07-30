"""Unit tests for :mod:`devmind.domain.similarity`."""

from __future__ import annotations

import math

import pytest

from devmind.domain.similarity import cosine_similarity
from devmind.domain.value_objects import Embedding

MODEL = "all-minilm-l6-v2"


def vector(*components: float) -> Embedding:
    return Embedding(model=MODEL, vector=components)


def test_identical_direction_scores_one() -> None:
    assert cosine_similarity(vector(1.0, 0.0), vector(2.0, 0.0)) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero() -> None:
    assert cosine_similarity(vector(1.0, 0.0), vector(0.0, 1.0)) == pytest.approx(0.0)


def test_opposite_direction_is_clamped_to_zero() -> None:
    assert cosine_similarity(vector(1.0, 0.0), vector(-1.0, 0.0)) == 0.0


def test_a_partial_match_falls_between_zero_and_one() -> None:
    similarity = cosine_similarity(vector(1.0, 0.0), vector(1.0, 1.0))

    assert similarity == pytest.approx(math.sqrt(2) / 2)


def test_similarity_is_symmetric() -> None:
    a, b = vector(0.3, 0.4), vector(0.8, 0.1)

    assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))


def test_magnitude_does_not_affect_direction() -> None:
    assert cosine_similarity(vector(1.0, 0.0), vector(5.0, 0.0)) == pytest.approx(1.0)


def test_a_zero_magnitude_vector_scores_zero() -> None:
    assert cosine_similarity(vector(1.0, 1.0), vector(0.0, 0.0)) == 0.0


def test_two_zero_magnitude_vectors_score_zero() -> None:
    assert cosine_similarity(vector(0.0, 0.0), vector(0.0, 0.0)) == 0.0


def test_a_vector_compared_to_itself_never_exceeds_one() -> None:
    identical = vector(0.1, 0.2, 0.3, 0.4)

    assert cosine_similarity(identical, identical) <= 1.0


def test_mismatched_dimensions_are_rejected() -> None:
    with pytest.raises(ValueError, match="different dimensions"):
        cosine_similarity(vector(1.0, 0.0), vector(1.0, 0.0, 0.0))
