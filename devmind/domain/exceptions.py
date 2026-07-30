"""Domain level errors raised while working with source documents.

Every error inherits from :class:`DevMindError`, so a caller may either
react to a specific failure or guard the whole boundary with a single
``except DevMindError`` clause.
"""

from __future__ import annotations

from devmind.core.exceptions import DevMindError

__all__ = [
    "DocumentError",
    "DocumentNotFoundError",
    "DocumentParseError",
    "DocumentTooLargeError",
    "EmbeddingError",
    "EmptyDocumentError",
    "GenerationError",
    "StorageError",
    "UnsupportedFormatError",
]


class DocumentError(DevMindError):
    """Base class for every document related failure."""


class DocumentNotFoundError(DocumentError):
    """Raised when the requested source file does not exist."""


class UnsupportedFormatError(DocumentError):
    """Raised when no parser is able to handle the given file type."""


class DocumentTooLargeError(DocumentError):
    """Raised when a file exceeds the configured ingestion size limit."""


class DocumentParseError(DocumentError):
    """Raised when a file is unreadable, corrupted or password protected."""


class EmptyDocumentError(DocumentParseError):
    """Raised when a file contains no extractable text.

    Typically caused by scanned or image-only documents, which carry no
    text layer and would silently pollute the index with empty entries.
    """


class StorageError(DevMindError):
    """Raised when the knowledge base cannot be read or written.

    Repository contracts are declared by the domain, so the failure mode
    they promise belongs here rather than to a specific database
    technology.
    """


class EmbeddingError(DevMindError):
    """Raised when text cannot be turned into a vector.

    Covers an unreachable or failing model service as well as a reply
    that does not match the request.
    """


class GenerationError(DevMindError):
    """Raised when a grounded answer cannot be produced.

    Covers an unreachable or failing chat model service as well as a
    reply that carries no usable text.
    """
