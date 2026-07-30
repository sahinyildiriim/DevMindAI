"""A fully composed request to the chat model."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Prompt"]


@dataclass(frozen=True, slots=True)
class Prompt:
    """The two parts a chat completion request is built from.

    Keeping them separate - rather than one concatenated string - lets
    the grounding rules live in ``system`` where a well-behaved model
    weighs them most heavily, and keeps the boundary between instruction
    and user-facing question explicit all the way to the request.

    Attributes:
        system: Grounding and behaviour instructions for the model.
        user: The context and the question the model must answer from.
    """

    system: str
    user: str
