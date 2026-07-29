"""Embedding providers backed by Microsoft Foundry Local."""

from devmind.infrastructure.embeddings.foundry_provider import (
    FoundryEmbeddingProvider,
    build_embedding_provider,
)

__all__ = ["FoundryEmbeddingProvider", "build_embedding_provider"]
