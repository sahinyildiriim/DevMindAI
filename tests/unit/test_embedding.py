"""Unit tests for the embedding value object and its binary format."""

from __future__ import annotations

import math

import pytest

from devmind.core.exceptions import DevMindError
from devmind.domain.exceptions import StorageError
from devmind.domain.value_objects import Embedding
from devmind.infrastructure.persistence.serialization import decode_vector, encode_vector


def test_embedding_reports_its_dimensions() -> None:
    embedding = Embedding(model="all-minilm-l6-v2", vector=(0.1, 0.2, 0.3))

    assert embedding.dimensions == 3


@pytest.mark.parametrize(
    ("model", "vector", "message"),
    [
        ("", (0.1,), "model must not be empty"),
        ("   ", (0.1,), "model must not be empty"),
        ("model", (), "vector must not be empty"),
        ("model", (0.1, math.nan), "finite numbers"),
        ("model", (math.inf,), "finite numbers"),
    ],
)
def test_embedding_rejects_unusable_vectors(
    model: str, vector: tuple[float, ...], message: str
) -> None:
    with pytest.raises(DevMindError, match=message):
        Embedding(model=model, vector=vector)


def test_embedding_is_immutable() -> None:
    embedding = Embedding(model="model", vector=(0.1,))

    with pytest.raises(AttributeError):
        embedding.model = "other"  # type: ignore[misc]


def test_vector_survives_a_storage_round_trip() -> None:
    vector = (0.0, -1.5, 3.25, 0.125)

    assert decode_vector(encode_vector(vector)) == vector


def test_vector_round_trip_keeps_single_precision() -> None:
    vector = tuple(index / 7 for index in range(64))

    decoded = decode_vector(encode_vector(vector))

    assert len(decoded) == len(vector)
    assert decoded == pytest.approx(vector, rel=1e-6)


def test_encoded_vector_uses_four_bytes_per_component() -> None:
    assert len(encode_vector((1.0, 2.0, 3.0))) == 12


@pytest.mark.parametrize("blob", [b"", b"abc", b"12345"])
def test_truncated_blobs_are_rejected(blob: bytes) -> None:
    with pytest.raises(StorageError, match="corrupt"):
        decode_vector(blob)


def test_components_out_of_single_precision_range_are_rejected() -> None:
    with pytest.raises(StorageError, match="out of range"):
        encode_vector((0.5, 1e39))
