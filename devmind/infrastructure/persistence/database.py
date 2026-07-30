"""Connection and transaction management for the SQLite knowledge base.

Every repository talks to the database through this gateway, which owns
the connection lifecycle, applies the pragmas the application depends on
and translates ``sqlite3`` failures into :class:`StorageError`. No other
module imports ``sqlite3``.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Final

from devmind.core.config import DatabaseConfig, get_settings
from devmind.core.logger import get_logger
from devmind.domain.exceptions import StorageError
from devmind.infrastructure.persistence.schema import (
    SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
)

__all__ = ["SqliteDatabase", "build_database"]

_logger = get_logger(__name__)

_PRAGMAS: Final[tuple[str, ...]] = (
    # Readers never block the single writer, which matters because
    # Streamlit serves every interaction from its own thread.
    "PRAGMA journal_mode = WAL",
    # Off by default in SQLite, and required for the cascades the schema
    # relies on. It is a per-connection setting.
    "PRAGMA foreign_keys = ON",
    # Wait for a competing writer instead of failing immediately.
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
)

_Parameters = Sequence[object]


class SqliteDatabase:
    """A SQLite database with one connection per thread.

    ``sqlite3`` connections must not be shared between threads. Rather
    than serialising every access behind a lock, each thread lazily
    opens its own connection; write-ahead logging keeps concurrent
    readers and the single writer out of each other's way.
    """

    def __init__(self, path: Path) -> None:
        """Initialise the gateway.

        Args:
            path: Location of the database file. Its parent directory is
                created on first connection.
        """
        self._path = path
        self._local = threading.local()

    @property
    def path(self) -> Path:
        """Location of the database file."""
        return self._path

    def connect(self) -> sqlite3.Connection:
        """Return the connection of the calling thread, opening it once.

        Returns:
            A configured connection.

        Raises:
            StorageError: If the database cannot be opened.
        """
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._open()
            self._local.connection = connection
        return connection

    def close(self) -> None:
        """Close the connection held by the calling thread, if any."""
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is not None:
            with suppress(sqlite3.Error):
                connection.close()
            self._local.connection = None

    def initialize(self) -> None:
        """Create the schema and verify its version.

        Running this on an up-to-date database is a no-op, so it is safe
        to call at every start-up.

        Raises:
            StorageError: If the schema cannot be created, or if the
                database was written by an incompatible version.
        """
        with self.transaction() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = ?", (SCHEMA_VERSION_KEY,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    (SCHEMA_VERSION_KEY, SCHEMA_VERSION),
                )
                _logger.info(
                    "Created knowledge base schema v%s at '%s'", SCHEMA_VERSION, self._path
                )
            elif row["value"] != SCHEMA_VERSION:
                raise StorageError(
                    f"Knowledge base at '{self._path}' uses schema v{row['value']}, "
                    f"but this build expects v{SCHEMA_VERSION}."
                )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block of statements as one atomic unit.

        The write lock is taken upfront, so two concurrent writers fail
        fast instead of deadlocking halfway through.

        Yields:
            The connection to run statements on.

        Raises:
            StorageError: If the transaction cannot be started, or if a
                statement inside it fails.
        """
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StorageError(f"Could not start a transaction: {exc}") from exc

        try:
            yield connection
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback(connection)
            raise StorageError(f"Transaction failed: {exc}") from exc
        except BaseException:
            self._rollback(connection)
            raise

    def execute(self, sql: str, parameters: _Parameters = ()) -> int:
        """Run a single statement in its own transaction.

        Args:
            sql: Statement to run, with placeholders for every value.
            parameters: Values bound to the placeholders.

        Returns:
            The number of rows the statement affected.

        Raises:
            StorageError: If the statement fails.
        """
        with self.transaction() as connection:
            return connection.execute(sql, parameters).rowcount

    def execute_many(self, sql: str, parameters: Sequence[_Parameters]) -> int:
        """Run one statement for each parameter set, in one transaction.

        Args:
            sql: Statement to run, with placeholders for every value.
            parameters: One sequence of values per execution.

        Returns:
            The number of rows the statements affected.

        Raises:
            StorageError: If any statement fails.
        """
        if not parameters:
            return 0
        with self.transaction() as connection:
            return connection.executemany(sql, parameters).rowcount

    def fetch_one(self, sql: str, parameters: _Parameters = ()) -> sqlite3.Row | None:
        """Read the first row of a query.

        Args:
            sql: Query to run, with placeholders for every value.
            parameters: Values bound to the placeholders.

        Returns:
            The first row, or ``None`` when the query yields nothing.

        Raises:
            StorageError: If the query fails.
        """
        try:
            row: sqlite3.Row | None = self.connect().execute(sql, parameters).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"Query failed: {exc}") from exc
        return row

    def fetch_all(self, sql: str, parameters: _Parameters = ()) -> list[sqlite3.Row]:
        """Read every row of a query.

        Args:
            sql: Query to run, with placeholders for every value.
            parameters: Values bound to the placeholders.

        Returns:
            The matching rows.

        Raises:
            StorageError: If the query fails.
        """
        try:
            return self.connect().execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Query failed: {exc}") from exc

    def count(self, sql: str, parameters: _Parameters = ()) -> int:
        """Run a ``SELECT COUNT(*) AS total ...`` query and return the count.

        Every repository that reports a size funnels through this one
        method, rather than each repeating ``int(row["total"])``.

        Args:
            sql: Query selecting a single column aliased ``total``.
            parameters: Values bound to the placeholders.

        Returns:
            The count. A bare aggregate query always yields exactly one
            row, but a fallback to 0 is kept rather than trusted as an
            invariant, since nothing here enforces what ``sql`` contains.

        Raises:
            StorageError: If the query fails.
        """
        row = self.fetch_one(sql, parameters)
        return int(row["total"]) if row is not None else 0

    def _open(self) -> sqlite3.Connection:
        """Open and configure a connection for the calling thread.

        Returns:
            The new connection.

        Raises:
            StorageError: If the database cannot be opened.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self._path, isolation_level=None)
            connection.row_factory = sqlite3.Row
            for pragma in _PRAGMAS:
                connection.execute(pragma)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(
                f"Could not open the knowledge base at '{self._path}': {exc}"
            ) from exc
        _logger.debug("Opened knowledge base connection to '%s'", self._path)
        return connection

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        """Roll a transaction back without masking the original error."""
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")


def build_database(config: DatabaseConfig | None = None) -> SqliteDatabase:
    """Open the knowledge base and make sure its schema is present.

    Args:
        config: Database settings to apply. Defaults to the active
            application settings.

    Returns:
        A ready to use database gateway.

    Raises:
        StorageError: If the database cannot be opened or initialised.
    """
    database = SqliteDatabase((config if config is not None else get_settings().database).path)
    database.initialize()
    return database
