"""Vector representation of a chunk of text."""

from __future__ import annotations

import math
from dataclasses import dataclass

from devmind.core.exceptions import DevMindError

__all__ = ["Embedding"]


@dataclass(frozen=True, slots=True)
class Embedding:
    """A dense vector produced by an embedding model.

    The model name travels with the vector because vectors are only
    comparable when they come from the same model: replacing the model
    invalidates every embedding stored before the change.

    Attributes:
        model: Identifier of the model that produced the vector.
        vector: The vector components, in model order.
    """

    model: str
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        """Validate the invariants of the embedding.

        Raises:
            DevMindError: If the model is unnamed, the vector is empty
                or any component is not a finite number.
        """
        if not self.model.strip():
            raise DevMindError("Embedding model must not be empty.")
        if not self.vector:
            raise DevMindError("Embedding vector must not be empty.")
        if not all(math.isfinite(component) for component in self.vector):
            raise DevMindError("Embedding vector must contain finite numbers only.")

    @property
    def dimensions(self) -> int:
        """Number of components in the vector."""
        return len(self.vector)
