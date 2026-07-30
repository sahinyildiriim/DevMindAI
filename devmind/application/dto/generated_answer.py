"""The outcome of answering a query: an answer plus what it is based on."""

from __future__ import annotations

from dataclasses import dataclass

from devmind.application.dto.search_result import SearchResult

__all__ = ["GeneratedAnswer"]


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """A grounded answer, together with the chunks it was grounded in.

    Attributes:
        text: The answer text, either produced by the chat model or the
            fixed refusal used when no context was found.
        citations: The chunks given to the model as context, in the same
            order they were presented, each with its confidence score.
            Empty exactly when ``text`` is the refusal: attribution
            reflects what the model was actually shown, not what it
            claims to have used.
    """

    text: str
    citations: tuple[SearchResult, ...]

    @property
    def is_grounded(self) -> bool:
        """Whether the answer is backed by at least one citation."""
        return bool(self.citations)
