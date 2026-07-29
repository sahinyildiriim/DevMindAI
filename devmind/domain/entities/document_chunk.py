"""A retrievable slice of a parsed document."""

from __future__ import annotations

from dataclasses import dataclass

from devmind.core.exceptions import DevMindError
from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = ["DocumentChunk"]


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A contiguous slice of a document, ready to be indexed.

    A chunk carries the metadata of the document it was cut from, so
    that retrieval can attribute an answer to its source without a
    second lookup, and it records its own position, so that a citation
    can point back at the exact passage.

    Attributes:
        chunk_id: Deterministic identity of this chunk.
        content: Text of the slice, free of surrounding whitespace.
        index: Zero based position of the chunk within its document.
        start_offset: Index of the first character in the document text.
        end_offset: Index just past the last character, so that
            ``document.content[start_offset:end_offset] == content``.
        metadata: Metadata of the source document, carried unchanged.
    """

    chunk_id: ChunkId
    content: str
    index: int
    start_offset: int
    end_offset: int
    metadata: DocumentMetadata

    def __post_init__(self) -> None:
        """Validate the invariants of the chunk.

        Raises:
            DevMindError: If the chunk is blank or its offsets do not
                describe its content.
        """
        if not self.content.strip():
            raise DevMindError(f"Chunk {self.chunk_id} carries no text.")
        if self.index < 0:
            raise DevMindError("Chunk index must not be negative.")
        if self.start_offset < 0:
            raise DevMindError("Chunk start offset must not be negative.")
        if self.end_offset - self.start_offset != len(self.content):
            raise DevMindError(
                f"Chunk {self.chunk_id} offsets ({self.start_offset}, {self.end_offset}) "
                f"do not match its content length of {len(self.content)}."
            )

    @property
    def character_count(self) -> int:
        """Number of characters in the chunk."""
        return len(self.content)
