"""Embedding provider backed by Microsoft Foundry Local.

Foundry Local serves an OpenAI-compatible API on the loopback
interface, so the adapter speaks to it through the ``openai`` client
rather than through a bespoke HTTP layer. Nothing leaves the machine.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from time import perf_counter

import openai
from openai import OpenAI

from devmind.application.interfaces.embedding_provider import EmbeddingProvider
from devmind.core.config import FoundryConfig, get_settings
from devmind.core.exceptions import DevMindError
from devmind.core.logger import get_logger
from devmind.domain.exceptions import EmbeddingError
from devmind.domain.value_objects.embedding import Embedding
from devmind.infrastructure.foundry_client import translate_openai_error

__all__ = ["FoundryEmbeddingProvider", "build_embedding_provider"]

_logger = get_logger(__name__)


class FoundryEmbeddingProvider(EmbeddingProvider):
    """Embeds text through a locally running Foundry Local model."""

    def __init__(self, client: OpenAI, model: str, batch_size: int) -> None:
        """Initialise the provider.

        Args:
            client: Client pointed at the Foundry Local endpoint.
            model: Identifier of the embedding model to call.
            batch_size: Maximum number of texts per request. Callers may
                pass any number of texts to :meth:`embed`; they are
                split into requests of this size.

        Raises:
            ValueError: If the model is unnamed or the batch size is not
                positive.
        """
        if not model.strip():
            raise ValueError("Embedding model must not be empty.")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be greater than zero.")
        self._client = client
        self._model = model
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        """Identifier of the model behind this provider."""
        return self._model

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """Embed a batch of texts, one request per ``batch_size`` texts.

        Args:
            texts: The texts to embed. None of them may be blank.

        Returns:
            One embedding per input text, in the same order.

        Raises:
            EmbeddingError: If a text is blank, if Foundry Local is
                unreachable or failing, or if a reply does not hold
                exactly one vector per input.
        """
        if not texts:
            return ()
        self._reject_blank(texts)

        embeddings: list[Embedding] = []
        for batch in self._batches(texts):
            embeddings.extend(self._embed_batch(batch))
        return tuple(embeddings)

    def _embed_batch(self, batch: Sequence[str]) -> tuple[Embedding, ...]:
        """Send one request and turn its reply into embeddings.

        Args:
            batch: Texts of a single request.

        Returns:
            The embeddings of the batch, in input order.

        Raises:
            EmbeddingError: If the request fails or the reply does not
                match it.
        """
        started_at = perf_counter()
        try:
            response = self._client.embeddings.create(model=self._model, input=list(batch))
        except openai.OpenAIError as exc:
            raise translate_openai_error(
                exc,
                error_type=EmbeddingError,
                kind="embedding",
                model=self._model,
                base_url=str(self._client.base_url),
            ) from exc

        # The API is free to reply out of order, so entries are placed
        # back by their declared index rather than by arrival.
        items = sorted(response.data, key=lambda item: item.index)
        if len(items) != len(batch):
            raise EmbeddingError(
                f"Model '{self._model}' returned {len(items)} vectors for {len(batch)} texts."
            )

        _logger.debug(
            "Embedded %d texts with '%s' in %.3fs",
            len(batch),
            self._model,
            perf_counter() - started_at,
        )
        return tuple(self._to_embedding(item.embedding) for item in items)

    def _to_embedding(self, vector: Sequence[float]) -> Embedding:
        """Wrap a raw vector, stamping it with this provider's model.

        Args:
            vector: Components returned by the model.

        Returns:
            The embedding.

        Raises:
            EmbeddingError: If the model returned an unusable vector.
        """
        try:
            return Embedding(model=self._model, vector=tuple(vector))
        except (TypeError, ValueError, DevMindError) as exc:
            raise EmbeddingError(
                f"Model '{self._model}' returned an unusable vector: {exc}"
            ) from exc

    def _batches(self, texts: Sequence[str]) -> Iterator[Sequence[str]]:
        """Split texts into request sized batches.

        Args:
            texts: All texts to embed.

        Yields:
            Slices of at most ``batch_size`` texts.
        """
        for start in range(0, len(texts), self._batch_size):
            yield texts[start : start + self._batch_size]

    @staticmethod
    def _reject_blank(texts: Sequence[str]) -> None:
        """Refuse a batch holding text with nothing to embed.

        Args:
            texts: The texts about to be sent.

        Raises:
            EmbeddingError: If any text is blank.
        """
        for position, text in enumerate(texts):
            if not text.strip():
                raise EmbeddingError(
                    f"Text at position {position} is blank and cannot be embedded."
                )


def build_embedding_provider(config: FoundryConfig | None = None) -> FoundryEmbeddingProvider:
    """Create the provider configured for this installation.

    Args:
        config: Foundry Local settings to apply. Defaults to the active
            application settings.

    Returns:
        A provider talking to the configured endpoint.
    """
    foundry = config if config is not None else get_settings().foundry
    client = OpenAI(
        base_url=foundry.endpoint,
        api_key=foundry.api_key,
        timeout=foundry.timeout_seconds,
        max_retries=foundry.max_retries,
    )
    return FoundryEmbeddingProvider(
        client=client, model=foundry.embedding_model, batch_size=foundry.embedding_batch_size
    )
