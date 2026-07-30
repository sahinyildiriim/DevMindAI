"""Parse, chunk and store a single document."""

from __future__ import annotations

from pathlib import Path

from devmind.application.dto.indexing_result import IndexingResult
from devmind.application.interfaces.document_parser import DocumentParserRegistry
from devmind.application.interfaces.text_chunker import TextChunker
from devmind.core.logger import get_logger
from devmind.domain.repositories.chunk_repository import ChunkRepository
from devmind.domain.repositories.document_repository import DocumentRepository

__all__ = ["IndexDocumentUseCase"]

_logger = get_logger(__name__)


class IndexDocumentUseCase:
    """Turns a source file into stored, retrievable chunks.

    Re-indexing a document whose content has not changed - same
    checksum as what is already stored - skips chunking and storage
    entirely: chunk identifiers are derived from the checksum, so
    redoing the work would only reproduce the rows already there.
    Embedding new chunks is a separate concern, handled afterwards by
    :class:`~devmind.application.use_cases.embed_chunks.EmbedChunksUseCase`
    over the whole knowledge base rather than one document at a time,
    so several newly indexed documents are embedded together in one run.

    Known limitation: saving the document and replacing its chunks are
    two separate writes, each atomic on its own but not atomic together.
    A failure between them - possible only from a genuine storage fault,
    since the document is guaranteed to exist by the time chunks are
    replaced - would leave the stored metadata ahead of its chunks. A
    later successful re-index of the same file corrects it. Closing that
    window for good would need the repositories to share one
    transaction across the two calls, which is more machinery than this
    failure mode's low likelihood currently justifies.
    """

    def __init__(
        self,
        parsers: DocumentParserRegistry,
        chunker: TextChunker,
        documents: DocumentRepository,
        chunks: ChunkRepository,
    ) -> None:
        """Initialise the use case.

        Args:
            parsers: Resolves the parser for a source file.
            chunker: Splits a parsed document into chunks.
            documents: Stores document metadata.
            chunks: Stores the chunks derived from a document.
        """
        self._parsers = parsers
        self._chunker = chunker
        self._documents = documents
        self._chunks = chunks

    def execute(self, source_path: Path) -> IndexingResult:
        """Index a single file.

        Args:
            source_path: Path of the file to index.

        Returns:
            What indexing accomplished.

        Raises:
            DocumentNotFoundError: If the path does not point to a file.
            UnsupportedFormatError: If no parser handles the file type.
            DocumentTooLargeError: If the file exceeds the size limit.
            DocumentParseError: If the file cannot be read or contains
                no extractable text.
            StorageError: If the knowledge base cannot be read or
                written.
        """
        parser = self._parsers.get_parser(source_path)
        document = parser.parse(source_path)
        metadata = document.metadata

        existing = self._documents.get(metadata.source_path)
        if existing is not None and existing.checksum == metadata.checksum:
            _logger.info("'%s' is unchanged; skipping re-indexing", metadata.file_name)
            return IndexingResult(metadata=existing, chunks_indexed=0, was_skipped=True)

        self._documents.save(metadata)
        chunks = self._chunker.chunk(document)
        self._chunks.replace_for_document(metadata.source_path, chunks)

        _logger.info("Indexed '%s' into %d chunk(s)", metadata.file_name, len(chunks))
        return IndexingResult(metadata=metadata, chunks_indexed=len(chunks), was_skipped=False)
