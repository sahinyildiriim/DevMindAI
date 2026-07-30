"""Chat completion clients backed by Microsoft Foundry Local."""

from devmind.infrastructure.llm.foundry_chat_provider import (
    FoundryChatProvider,
    build_chat_provider,
)

__all__ = ["FoundryChatProvider", "build_chat_provider"]
