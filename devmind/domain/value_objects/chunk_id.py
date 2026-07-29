"""Stable identity of a single chunk of a document."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from devmind.core.exceptions import DevMindError

__all__ = ["ChunkId"]

_CHECKSUM_PREFIX_LENGTH: Final[int] = 16
_INDEX_DIGITS: Final[int] = 4
_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^[0-9a-f]{{{_CHECKSUM_PREFIX_LENGTH}}}-\d{{{_INDEX_DIGITS},}}$"
)


@dataclass(frozen=True, slots=True)
class ChunkId:
    """Identifier of a chunk, derived from its document and position.

    The identifier is deterministic: re-ingesting an unchanged document
    produces exactly the same identifiers, which lets later stages
    replace an existing index entry instead of duplicating it. Editing
    the document changes its checksum, and therefore every identifier
    derived from it.

    Attributes:
        value: The identifier itself, formatted as
            ``<checksum prefix>-<zero padded index>``.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate the identifier format.

        Raises:
            DevMindError: If the value is not a well formed chunk id.
        """
        if not _ID_PATTERN.match(self.value):
            raise DevMindError(f"Malformed chunk id: {self.value!r}.")

    @classmethod
    def for_document(cls, document_checksum: str, index: int) -> ChunkId:
        """Derive the identifier of the ``index``-th chunk of a document.

        Args:
            document_checksum: SHA-256 digest of the source document.
            index: Zero based position of the chunk within the document.

        Returns:
            The derived identifier.

        Raises:
            DevMindError: If the checksum is too short or the index is
                negative.
        """
        if len(document_checksum) < _CHECKSUM_PREFIX_LENGTH:
            raise DevMindError(
                f"Document checksum must be at least {_CHECKSUM_PREFIX_LENGTH} characters."
            )
        if index < 0:
            raise DevMindError("Chunk index must not be negative.")
        prefix = document_checksum[:_CHECKSUM_PREFIX_LENGTH].lower()
        return cls(f"{prefix}-{index:0{_INDEX_DIGITS}d}")

    def __str__(self) -> str:
        """Return the identifier as plain text."""
        return self.value
