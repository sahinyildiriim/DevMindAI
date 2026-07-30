"""Chat completion provider backed by Microsoft Foundry Local.

Foundry Local serves an OpenAI-compatible API on the loopback
interface, so the adapter speaks to it through the ``openai`` client
rather than through a bespoke HTTP layer. Nothing leaves the machine.
"""

from __future__ import annotations

import openai
from openai import OpenAI

from devmind.application.dto.prompt import Prompt
from devmind.application.interfaces.chat_provider import ChatProvider
from devmind.core.config import FoundryConfig, get_settings
from devmind.core.logger import get_logger
from devmind.domain.exceptions import GenerationError
from devmind.infrastructure.foundry_client import translate_openai_error

__all__ = ["FoundryChatProvider", "build_chat_provider"]

_logger = get_logger(__name__)


class FoundryChatProvider(ChatProvider):
    """Generates completions through a locally running Foundry Local model."""

    def __init__(self, client: OpenAI, model: str, max_tokens: int, temperature: float) -> None:
        """Initialise the provider.

        Args:
            client: Client pointed at the Foundry Local endpoint.
            model: Identifier of the chat model to call.
            max_tokens: Upper bound on the length of a generated answer.
            temperature: Sampling temperature passed to the model.

        Raises:
            ValueError: If the model is unnamed, ``max_tokens`` is not
                positive, or ``temperature`` is out of the [0, 2] range
                the API accepts.
        """
        if not model.strip():
            raise ValueError("Chat model must not be empty.")
        if max_tokens <= 0:
            raise ValueError("Max tokens must be greater than zero.")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0.")
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def model(self) -> str:
        """Identifier of the chat model behind this provider."""
        return self._model

    def complete(self, prompt: Prompt) -> str:
        """Generate a completion for ``prompt``.

        Args:
            prompt: The system and user parts of the request.

        Returns:
            The model's answer text, stripped of surrounding whitespace.

        Raises:
            GenerationError: If Foundry Local is unreachable or failing,
                or if it returns no usable text.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except openai.OpenAIError as exc:
            raise translate_openai_error(
                exc,
                error_type=GenerationError,
                kind="chat",
                model=self._model,
                base_url=str(self._client.base_url),
            ) from exc

        return self._extract_text(response)

    def _extract_text(self, response: openai.types.chat.ChatCompletion) -> str:
        """Read the generated text out of a chat completion reply.

        Args:
            response: Reply returned by the client.

        Returns:
            The answer text, stripped of surrounding whitespace.

        Raises:
            GenerationError: If the reply holds no choice, or the choice
                carries no text.
        """
        if not response.choices:
            raise GenerationError(f"Model '{self._model}' returned no choices.")

        text = response.choices[0].message.content
        if text is None or not text.strip():
            raise GenerationError(f"Model '{self._model}' returned an empty response.")

        _logger.debug("Generated a %d-character answer with '%s'", len(text), self._model)
        return text.strip()


def build_chat_provider(config: FoundryConfig | None = None) -> FoundryChatProvider:
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
    return FoundryChatProvider(
        client=client,
        model=foundry.chat_model,
        max_tokens=foundry.max_tokens,
        temperature=foundry.temperature,
    )
