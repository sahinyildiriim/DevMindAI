"""Port for turning a grounded prompt into an answer.

The abstraction lets the answer generation use case depend on *that a
prompt yields text* without depending on Microsoft Foundry Local, HTTP
or any particular chat model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from devmind.application.dto.prompt import Prompt

__all__ = ["ChatProvider"]


class ChatProvider(ABC):
    """Produces a single completion for a composed prompt."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Identifier of the chat model behind this provider."""

    @abstractmethod
    def complete(self, prompt: Prompt) -> str:
        """Generate a completion for ``prompt``.

        Args:
            prompt: The system and user parts of the request.

        Returns:
            The model's answer text, stripped of surrounding whitespace.

        Raises:
            GenerationError: If the model service is unreachable or
                failing, or if it returns no usable text.
        """
