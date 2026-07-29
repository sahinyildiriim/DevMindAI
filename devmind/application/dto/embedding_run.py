"""Outcome of an embedding run, as reported to the caller."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["EmbeddingRun"]


@dataclass(frozen=True, slots=True)
class EmbeddingRun:
    """What an embedding run accomplished.

    Attributes:
        model: Identifier of the model the run used.
        embedded: Number of chunks that received an embedding.
        batches: Number of batches the work was split into.
        duration_seconds: Wall clock duration of the run.
    """

    model: str
    embedded: int
    batches: int
    duration_seconds: float

    @property
    def had_work(self) -> bool:
        """Whether anything was pending when the run started."""
        return self.embedded > 0
