"""SQLite implementation of :class:`MetadataRepository`."""

from __future__ import annotations

from typing import Final

from devmind.domain.repositories.metadata_repository import MetadataRepository
from devmind.infrastructure.persistence.database import SqliteDatabase

__all__ = ["SqliteMetadataRepository"]

_UPSERT: Final[str] = """
    INSERT INTO metadata (key, value)
    VALUES (?, ?)
    ON CONFLICT (key) DO UPDATE SET value = excluded.value
"""


class SqliteMetadataRepository(MetadataRepository):
    """Stores knowledge base level state in the SQLite key/value table."""

    def __init__(self, database: SqliteDatabase) -> None:
        """Initialise the repository.

        Args:
            database: Gateway to the knowledge base.
        """
        self._database = database

    def put(self, key: str, value: str) -> None:
        """Store a value, replacing any previous value of the key.

        Args:
            key: Name of the entry.
            value: Value to store.

        Raises:
            ValueError: If the key is blank.
            StorageError: If the entry cannot be written.
        """
        if not key.strip():
            raise ValueError("Metadata key must not be blank.")
        self._database.execute(_UPSERT, (key, value))

    def get(self, key: str) -> str | None:
        """Read a value by key.

        Args:
            key: Name of the entry.

        Returns:
            The stored value, or ``None`` when the key is unknown.

        Raises:
            StorageError: If the entry cannot be read.
        """
        row = self._database.fetch_one("SELECT value FROM metadata WHERE key = ?", (key,))
        return str(row["value"]) if row is not None else None

    def items(self) -> dict[str, str]:
        """Read every entry, keyed by name.

        Returns:
            All stored entries, ordered by key.

        Raises:
            StorageError: If the entries cannot be read.
        """
        rows = self._database.fetch_all("SELECT key, value FROM metadata ORDER BY key")
        return {str(row["key"]): str(row["value"]) for row in rows}

    def delete(self, key: str) -> bool:
        """Remove an entry.

        Args:
            key: Name of the entry.

        Returns:
            ``True`` when an entry was removed.

        Raises:
            StorageError: If the entry cannot be removed.
        """
        return self._database.execute("DELETE FROM metadata WHERE key = ?", (key,)) > 0
