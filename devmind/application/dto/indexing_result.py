"""Outcome of indexing a single document."""

from __future__ import annotations

from dataclasses import dataclass

from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = ["IndexingResult"]


@dataclass(frozen=True, slots=True)
class IndexingResult:
    """What indexing a single document accomplished.

    Attributes:
        metadata: The document's stored metadata.
        chunks_indexed: Number of chunks written for this document. Zero
            when indexing was skipped because the document is unchanged.
        was_skipped: Whether an identical version of this document was
            already indexed, so chunking and storage were skipped.
    """

    metadata: DocumentMetadata
    chunks_indexed: int
    was_skipped: bool
