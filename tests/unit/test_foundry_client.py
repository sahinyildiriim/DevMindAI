"""Unit tests for the shared Foundry Local error translation helper."""

from __future__ import annotations

import httpx
import openai
import pytest

from devmind.domain.exceptions import EmbeddingError, GenerationError
from devmind.infrastructure.foundry_client import START_SERVICE_HINT, translate_openai_error

BASE_URL = "http://localhost:5273/v1"


def make_connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", f"{BASE_URL}/embeddings"))


def test_a_connection_failure_names_the_endpoint_and_the_hint() -> None:
    error = translate_openai_error(
        make_connection_error(),
        error_type=EmbeddingError,
        kind="embedding",
        model="all-minilm-l6-v2",
        base_url=BASE_URL,
    )

    assert isinstance(error, EmbeddingError)
    assert BASE_URL in str(error)
    assert START_SERVICE_HINT in str(error)
    assert "embedding model" in str(error)


def test_a_connection_failure_is_worded_for_the_given_kind() -> None:
    error = translate_openai_error(
        make_connection_error(),
        error_type=GenerationError,
        kind="chat",
        model="phi-3.5-mini",
        base_url=BASE_URL,
    )

    assert "chat model" in str(error)


def test_another_client_failure_names_the_model_and_the_original_error() -> None:
    original = openai.OpenAIError("the model is not loaded")

    error = translate_openai_error(
        original,
        error_type=EmbeddingError,
        kind="embedding",
        model="all-minilm-l6-v2",
        base_url=BASE_URL,
    )

    assert isinstance(error, EmbeddingError)
    assert "Embedding request" in str(error)
    assert "all-minilm-l6-v2" in str(error)
    assert "the model is not loaded" in str(error)


def test_the_returned_error_is_not_raised_by_the_helper_itself() -> None:
    # translate_openai_error only constructs the exception; the call site
    # keeps `raise ... from exc` so the original cause is preserved.
    error = translate_openai_error(
        make_connection_error(),
        error_type=EmbeddingError,
        kind="embedding",
        model="m",
        base_url=BASE_URL,
    )

    assert isinstance(error, Exception)
    with pytest.raises(EmbeddingError):
        raise error
