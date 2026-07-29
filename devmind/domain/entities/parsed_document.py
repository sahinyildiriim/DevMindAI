"""The common result model produced by every document parser."""

from __future__ import annotations

from dataclasses import dataclass

from devmind.domain.exceptions import EmptyDocumentError
from devmind.domain.value_objects.document_metadata import DocumentMetadata

__all__ = ["ParsedDocument"]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A source document reduced to plain text plus its metadata.

    This is the single hand-off point between the parser adapters and
    the rest of the pipeline: whatever the original format was, later
    stages only ever see normalised text and uniform metadata.

    Attributes:
        content: Normalised plain text extracted from the document.
        metadata: Description of the file the text was extracted from.
    """

    content: str
    metadata: DocumentMetadata

    def __post_init__(self) -> None:
        """Enforce that a parsed document always carries text.

        Raises:
            EmptyDocumentError: If no extractable text is present.
        """
        if not self.content.strip():
            raise EmptyDocumentError(
                f"No extractable text found in '{self.metadata.file_name}'. "
                "The document is empty or contains images only."
            )

    @property
    def character_count(self) -> int:
        """Number of characters in the extracted text."""
        return len(self.content)

    @property
    def word_count(self) -> int:
        """Number of whitespace separated words, computed on access."""
        return len(self.content.split())
