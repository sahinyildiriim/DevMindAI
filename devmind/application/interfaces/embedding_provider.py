"""Port for turning text into vectors.

The abstraction lets the indexing use case depend on *that text becomes
a vector* without depending on Microsoft Foundry Local, HTTP or any
particular model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from devmind.domain.value_objects.embedding import Embedding

__all__ = ["EmbeddingProvider"]


class EmbeddingProvider(ABC):
    """Produces embeddings for batches of text."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Identifier of the model behind this provider.

        Implementations must stamp this exact value on every embedding
        they return, so that stored vectors can always be matched back
        to the model that produced them.
        """

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        """Embed a batch of texts.

        Args:
            texts: The texts to embed. None of them may be blank.

        Returns:
            One embedding per input text, in the same order. Embedding
            an empty batch yields an empty result.

        Raises:
            EmbeddingError: If a text is blank, if the model service is
                unreachable or failing, or if the reply does not hold
                exactly one vector per input.
        """
