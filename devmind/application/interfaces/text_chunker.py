"""Port for splitting a parsed document into retrievable chunks.

The abstraction is owned by the application layer so that use cases can
depend on *that a document gets split* without depending on *how* it is
split.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from devmind.domain.entities.document_chunk import DocumentChunk
from devmind.domain.entities.parsed_document import ParsedDocument

__all__ = ["TextChunker"]


class TextChunker(ABC):
    """Splits a parsed document into chunks suitable for retrieval."""

    @abstractmethod
    def chunk(self, document: ParsedDocument) -> tuple[DocumentChunk, ...]:
        """Split a document into ordered chunks.

        Args:
            document: The parsed document to split.

        Returns:
            The chunks in reading order, indexed from zero. A parsed
            document always carries text, so the result is never empty.
        """
