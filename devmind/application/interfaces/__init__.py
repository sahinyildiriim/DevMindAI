"""Ports: abstractions the application depends on, owned by this layer."""

from devmind.application.interfaces.document_parser import DocumentParser, DocumentParserRegistry
from devmind.application.interfaces.embedding_provider import EmbeddingProvider
from devmind.application.interfaces.text_chunker import TextChunker

__all__ = ["DocumentParser", "DocumentParserRegistry", "EmbeddingProvider", "TextChunker"]
