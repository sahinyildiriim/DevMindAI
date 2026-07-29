"""Sliding window chunker with boundary aware cut points."""

from __future__ import annotations

from typing import Final

from devmind.application.interfaces.text_chunker import TextChunker
from devmind.core.config import RetrievalConfig, get_settings
from devmind.core.logger import get_logger
from devmind.domain.entities.document_chunk import DocumentChunk
from devmind.domain.entities.parsed_document import ParsedDocument
from devmind.domain.value_objects.chunk_id import ChunkId
from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = ["SlidingWindowChunker", "build_chunker"]

_logger = get_logger(__name__)

# Separators are tried in order, so a chunk breaks at the largest
# structural unit available near the size limit: a paragraph first, then
# a line, a sentence, and finally a word.
_SEPARATORS: Final[tuple[str, ...]] = ("\n\n", "\n", ". ", "! ", "? ", " ")

# How far back a cut point may be pulled to reach a separator. Beyond
# this the chunk would lose too much of its budget, so the text is cut
# exactly at the limit instead.
_LOOKBACK_RATIO: Final[float] = 0.2


class SlidingWindowChunker(TextChunker):
    """Cuts text into overlapping windows of a configurable size.

    Consecutive chunks share ``chunk_overlap`` characters, which keeps a
    sentence that straddles a cut point retrievable from both sides.
    """

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        """Initialise the chunker.

        Args:
            chunk_size: Maximum number of characters per chunk.
            chunk_overlap: Number of characters each chunk shares with
                its predecessor.

        Raises:
            ValueError: If the size is not positive, or if the overlap
                is negative or would prevent the window from advancing.
        """
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than zero.")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Chunk overlap must be non-negative and smaller than the chunk size.")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._lookback = max(1, int(chunk_size * _LOOKBACK_RATIO))

    def chunk(self, document: ParsedDocument) -> tuple[DocumentChunk, ...]:
        """Split a document into ordered, overlapping chunks.

        Args:
            document: The parsed document to split.

        Returns:
            The chunks in reading order, indexed from zero.
        """
        text = document.content
        chunks: list[DocumentChunk] = []
        start = 0

        while start < len(text):
            end = self._find_end(text, start)
            chunk = self._build_chunk(text, start, end, len(chunks), document.metadata)
            if chunk is not None:
                chunks.append(chunk)
            start = self._advance(start, end, len(text))

        _logger.info(
            "Split '%s' into %d chunks (size=%d, overlap=%d)",
            document.metadata.file_name,
            len(chunks),
            self._chunk_size,
            self._chunk_overlap,
        )
        return tuple(chunks)

    def _find_end(self, text: str, start: int) -> int:
        """Locate the cut point of the window opened at ``start``.

        Args:
            text: Full document text.
            start: Index the current window starts at.

        Returns:
            The index just past the last character of the window, moved
            back to the closest structural boundary when one is within
            reach.
        """
        limit = start + self._chunk_size
        if limit >= len(text):
            return len(text)

        window_start = max(start + 1, limit - self._lookback)
        window = text[window_start:limit]
        for separator in _SEPARATORS:
            position = window.rfind(separator)
            if position != -1:
                return window_start + position + len(separator)
        return limit

    def _advance(self, start: int, end: int, length: int) -> int:
        """Compute the start of the next window.

        Args:
            start: Start of the window that was just emitted.
            end: End of the window that was just emitted.
            length: Total length of the document text.

        Returns:
            The next start position. Progress of at least one character
            is guaranteed, so the loop always terminates even when a
            boundary adjustment shortens a window below the overlap.
        """
        if end >= length:
            return length
        return max(end - self._chunk_overlap, start + 1)

    @staticmethod
    def _build_chunk(
        text: str, start: int, end: int, index: int, metadata: DocumentMetadata
    ) -> DocumentChunk | None:
        """Build a chunk from a window, trimming surrounding whitespace.

        Offsets are corrected while trimming, so that slicing the
        document text with them reproduces the chunk content exactly.

        Args:
            text: Full document text.
            start: Start of the window.
            end: End of the window.
            index: Position of the chunk among the emitted chunks.
            metadata: Metadata of the source document.

        Returns:
            The chunk, or ``None`` when the window holds only
            whitespace.
        """
        window = text[start:end]
        content = window.strip()
        if not content:
            return None
        offset = start + (len(window) - len(window.lstrip()))
        return DocumentChunk(
            chunk_id=ChunkId.for_document(metadata.checksum, index),
            content=content,
            index=index,
            start_offset=offset,
            end_offset=offset + len(content),
            metadata=metadata,
        )


def build_chunker(config: RetrievalConfig | None = None) -> SlidingWindowChunker:
    """Create the chunker configured for this installation.

    Args:
        config: Retrieval settings to apply. Defaults to the active
            application settings.

    Returns:
        A chunker honouring the configured size and overlap.
    """
    retrieval = config if config is not None else get_settings().retrieval
    return SlidingWindowChunker(retrieval.chunk_size, retrieval.chunk_overlap)
