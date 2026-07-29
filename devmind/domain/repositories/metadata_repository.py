"""Persistence contract for knowledge base level metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["MetadataRepository"]


class MetadataRepository(ABC):
    """Stores facts about the knowledge base itself.

    This is a small key/value store for state that belongs to the index
    as a whole rather than to a single document: the schema version, the
    embedding model currently in use, the time of the last indexing run.
    """

    @abstractmethod
    def put(self, key: str, value: str) -> None:
        """Store a value, replacing any previous value of the key.

        Args:
            key: Name of the entry. Must not be blank.
            value: Value to store.

        Raises:
            StorageError: If the entry cannot be written.
        """

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Read a value by key.

        Args:
            key: Name of the entry.

        Returns:
            The stored value, or ``None`` when the key is unknown.

        Raises:
            StorageError: If the entry cannot be read.
        """

    @abstractmethod
    def items(self) -> dict[str, str]:
        """Read every entry, keyed by name.

        Returns:
            All stored entries.

        Raises:
            StorageError: If the entries cannot be read.
        """

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove an entry.

        Args:
            key: Name of the entry.

        Returns:
            ``True`` when an entry was removed.

        Raises:
            StorageError: If the entry cannot be removed.
        """
