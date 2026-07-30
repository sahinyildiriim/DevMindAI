"""Shared plumbing for adapters that talk to Foundry Local via ``openai``.

Both :class:`~devmind.infrastructure.embeddings.foundry_provider.FoundryEmbeddingProvider`
and :class:`~devmind.infrastructure.llm.foundry_chat_provider.FoundryChatProvider`
are thin wrappers around the same local, OpenAI-compatible endpoint, and
both fail in the same two ways: the service is not running, or the
request itself is rejected. This module gives that one piece of shared
behaviour one home instead of two copies that could drift apart.
"""

from __future__ import annotations

from typing import Final

import openai

from devmind.core.exceptions import DevMindError

__all__ = ["START_SERVICE_HINT", "translate_openai_error"]

START_SERVICE_HINT: Final[str] = (
    "Make sure Foundry Local is running: 'foundry service start', then check "
    "the endpoint with 'foundry service status'."
)


def translate_openai_error[T: DevMindError](
    exc: openai.OpenAIError,
    *,
    error_type: type[T],
    kind: str,
    model: str,
    base_url: str,
) -> T:
    """Translate an ``openai`` client failure into a domain error.

    Args:
        exc: The failure raised by the ``openai`` client.
        error_type: Domain exception to construct, e.g. ``EmbeddingError``
            or ``GenerationError``.
        kind: What the request was for, lowercase, e.g. ``"embedding"``
            or ``"chat"``. Used to word both messages below.
        model: Model identifier that was requested.
        base_url: Endpoint the client was pointed at.

    Returns:
        The constructed domain exception. Not raised: callers keep the
        ``raise ... from exc`` idiom at the call site, so the original
        failure stays attached as the cause.
    """
    if isinstance(exc, openai.APIConnectionError):
        return error_type(f"Cannot reach the {kind} model at '{base_url}'. {START_SERVICE_HINT}")
    return error_type(
        f"{kind.capitalize()} request to model '{model}' failed: {type(exc).__name__}: {exc}"
    )
