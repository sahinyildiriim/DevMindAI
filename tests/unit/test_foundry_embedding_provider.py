"""Unit tests for the Foundry Local embedding adapter."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
import pytest

from devmind.domain.exceptions import EmbeddingError
from devmind.infrastructure.embeddings import FoundryEmbeddingProvider

BASE_URL = "http://localhost:5273/v1"


@dataclass
class FakeItem:
    index: int
    embedding: list[float]


@dataclass
class FakeResponse:
    data: list[FakeItem]


@dataclass
class FakeEmbeddings:
    responder: Callable[[str, list[str]], FakeResponse]
    calls: list[list[str]] = field(default_factory=list)

    def create(self, *, model: str, input: list[str]) -> FakeResponse:  # noqa: A002
        self.calls.append(list(input))
        return self.responder(model, list(input))


class FakeClient:
    """Stands in for the OpenAI client the adapter talks through."""

    base_url = BASE_URL

    def __init__(self, responder: Callable[[str, list[str]], FakeResponse] | None = None) -> None:
        self.embeddings = FakeEmbeddings(responder or _one_vector_per_text)


def _one_vector_per_text(_model: str, texts: list[str]) -> FakeResponse:
    return FakeResponse(
        data=[
            FakeItem(index=position, embedding=[float(len(text)), 0.5])
            for position, text in enumerate(texts)
        ]
    )


def make_provider(client: Any, *, batch_size: int = 16) -> FoundryEmbeddingProvider:
    return FoundryEmbeddingProvider(client=client, model="all-minilm-l6-v2", batch_size=batch_size)


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_every_text_gets_a_vector_stamped_with_the_model() -> None:
    provider = make_provider(FakeClient())

    embeddings = provider.embed(["routing", "middleware"])

    assert len(embeddings) == 2
    assert [embedding.vector[0] for embedding in embeddings] == [7.0, 10.0]
    assert all(embedding.model == "all-minilm-l6-v2" for embedding in embeddings)


def test_the_reply_order_follows_the_declared_index() -> None:
    def shuffled(_model: str, texts: list[str]) -> FakeResponse:
        items = [
            FakeItem(index=position, embedding=[float(position)]) for position in range(len(texts))
        ]
        return FakeResponse(data=list(reversed(items)))

    embeddings = make_provider(FakeClient(shuffled)).embed(["a", "b", "c"])

    assert [embedding.vector[0] for embedding in embeddings] == [0.0, 1.0, 2.0]


def test_an_empty_batch_never_reaches_the_service() -> None:
    client = FakeClient()

    assert make_provider(client).embed([]) == ()
    assert client.embeddings.calls == []


# --------------------------------------------------------------------------- #
# Batching
# --------------------------------------------------------------------------- #
def test_texts_are_split_into_requests_of_the_configured_size() -> None:
    client = FakeClient()
    texts = [f"chunk {index}" for index in range(5)]

    embeddings = make_provider(client, batch_size=2).embed(texts)

    assert [len(call) for call in client.embeddings.calls] == [2, 2, 1]
    assert len(embeddings) == 5


def test_a_single_request_carries_everything_when_it_fits() -> None:
    client = FakeClient()

    make_provider(client, batch_size=16).embed(["a", "b", "c"])

    assert len(client.embeddings.calls) == 1


def test_batches_keep_the_original_order() -> None:
    texts = [f"text-{index}" for index in range(7)]

    embeddings = make_provider(FakeClient(), batch_size=3).embed(texts)

    assert [embedding.vector[0] for embedding in embeddings] == [float(len(text)) for text in texts]


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def test_an_unreachable_service_is_explained() -> None:
    def refuse(_model: str, _texts: list[str]) -> FakeResponse:
        raise openai.APIConnectionError(request=httpx.Request("POST", f"{BASE_URL}/embeddings"))

    with pytest.raises(EmbeddingError, match="foundry service start"):
        make_provider(FakeClient(refuse)).embed(["routing"])


def test_the_endpoint_is_named_when_the_service_is_unreachable() -> None:
    def refuse(_model: str, _texts: list[str]) -> FakeResponse:
        raise openai.APIConnectionError(request=httpx.Request("POST", f"{BASE_URL}/embeddings"))

    with pytest.raises(EmbeddingError, match="localhost:5273"):
        make_provider(FakeClient(refuse)).embed(["routing"])


def test_other_client_failures_are_wrapped() -> None:
    def fail(_model: str, _texts: list[str]) -> FakeResponse:
        raise openai.OpenAIError("the model is not loaded")

    with pytest.raises(EmbeddingError, match="the model is not loaded"):
        make_provider(FakeClient(fail)).embed(["routing"])


def test_a_reply_with_the_wrong_number_of_vectors_is_refused() -> None:
    def short(_model: str, _texts: list[str]) -> FakeResponse:
        return FakeResponse(data=[FakeItem(index=0, embedding=[0.1])])

    with pytest.raises(EmbeddingError, match="returned 1 vectors for 2 texts"):
        make_provider(FakeClient(short)).embed(["routing", "middleware"])


def test_an_empty_vector_is_refused() -> None:
    def empty(_model: str, texts: list[str]) -> FakeResponse:
        return FakeResponse(
            data=[FakeItem(index=position, embedding=[]) for position in range(len(texts))]
        )

    with pytest.raises(EmbeddingError, match="unusable vector"):
        make_provider(FakeClient(empty)).embed(["routing"])


@pytest.mark.parametrize("texts", [["routing", "   "], ["", "middleware"]])
def test_blank_text_is_refused_before_any_request(texts: Sequence[str]) -> None:
    client = FakeClient()

    with pytest.raises(EmbeddingError, match="blank"):
        make_provider(client).embed(texts)

    assert client.embeddings.calls == []


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("model", "batch_size", "message"),
    [
        ("", 16, "model must not be empty"),
        ("   ", 16, "model must not be empty"),
        ("model", 0, "batch size"),
        ("model", -1, "batch size"),
    ],
)
def test_invalid_settings_are_rejected(model: str, batch_size: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        FoundryEmbeddingProvider(client=FakeClient(), model=model, batch_size=batch_size)  # type: ignore[arg-type]
