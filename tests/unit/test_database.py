"""Unit tests for the SQLite gateway: schema, transactions and threading."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from devmind.core.config import DatabaseConfig
from devmind.domain.exceptions import StorageError
from devmind.infrastructure.persistence import SCHEMA_VERSION, SqliteDatabase, build_database
from devmind.infrastructure.persistence.schema import SCHEMA_VERSION_KEY

EXPECTED_TABLES = {"chunks", "documents", "embeddings", "metadata"}


def table_names(database: SqliteDatabase) -> set[str]:
    rows = database.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row["name"]) for row in rows}


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def test_initialize_creates_every_table(database: SqliteDatabase) -> None:
    assert table_names(database) >= EXPECTED_TABLES


def test_initialize_records_the_schema_version(database: SqliteDatabase) -> None:
    row = database.fetch_one("SELECT value FROM metadata WHERE key = ?", (SCHEMA_VERSION_KEY,))

    assert row is not None
    assert row["value"] == SCHEMA_VERSION


def test_initialize_is_idempotent(database: SqliteDatabase) -> None:
    database.initialize()
    database.initialize()

    assert table_names(database) >= EXPECTED_TABLES


def test_initialize_rejects_an_incompatible_schema(database: SqliteDatabase) -> None:
    database.execute("UPDATE metadata SET value = '99' WHERE key = ?", (SCHEMA_VERSION_KEY,))

    with pytest.raises(StorageError, match="schema v99"):
        database.initialize()


def test_build_database_creates_the_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "store" / "devmind.db"

    instance = build_database(DatabaseConfig(path=target))
    try:
        assert target.is_file()
        assert table_names(instance) >= EXPECTED_TABLES
    finally:
        instance.close()


# --------------------------------------------------------------------------- #
# Integrity and transactions
# --------------------------------------------------------------------------- #
def test_foreign_keys_are_enforced(database: SqliteDatabase) -> None:
    with pytest.raises(StorageError, match="FOREIGN KEY"):
        database.execute(
            """
            INSERT INTO chunks (chunk_id, document_id, chunk_index, content,
                                start_offset, end_offset)
            VALUES ('a1b2c3d4e5f60718-0000', 999, 0, 'orphan', 0, 6)
            """
        )


def test_a_failing_transaction_leaves_no_trace(database: SqliteDatabase) -> None:
    with pytest.raises(RuntimeError), database.transaction() as connection:
        connection.execute("INSERT INTO metadata (key, value) VALUES ('half', 'written')")
        raise RuntimeError("the caller gave up")

    assert database.fetch_one("SELECT value FROM metadata WHERE key = 'half'") is None


def test_a_successful_transaction_is_committed(database: SqliteDatabase) -> None:
    with database.transaction() as connection:
        connection.execute("INSERT INTO metadata (key, value) VALUES ('done', 'yes')")

    row = database.fetch_one("SELECT value FROM metadata WHERE key = 'done'")
    assert row is not None
    assert row["value"] == "yes"


def test_execute_reports_the_number_of_affected_rows(database: SqliteDatabase) -> None:
    database.execute("INSERT INTO metadata (key, value) VALUES ('a', '1')")

    assert database.execute("DELETE FROM metadata WHERE key = 'a'") == 1
    assert database.execute("DELETE FROM metadata WHERE key = 'a'") == 0


def test_execute_many_without_parameters_does_nothing(database: SqliteDatabase) -> None:
    assert database.execute_many("INSERT INTO metadata (key, value) VALUES (?, ?)", []) == 0


def test_invalid_statements_are_reported_as_storage_errors(database: SqliteDatabase) -> None:
    with pytest.raises(StorageError, match="Query failed"):
        database.fetch_all("SELECT * FROM there_is_no_such_table")


def test_fetch_one_returns_none_when_nothing_matches(database: SqliteDatabase) -> None:
    assert database.fetch_one("SELECT value FROM metadata WHERE key = 'absent'") is None


# --------------------------------------------------------------------------- #
# count()
# --------------------------------------------------------------------------- #
def test_count_reads_the_aggregate_column(database: SqliteDatabase) -> None:
    database.execute("INSERT INTO metadata (key, value) VALUES ('a', '1')")
    database.execute("INSERT INTO metadata (key, value) VALUES ('b', '2')")

    assert database.count("SELECT COUNT(*) AS total FROM metadata") == 3  # +1 schema_version


def test_count_applies_bound_parameters(database: SqliteDatabase) -> None:
    database.execute("INSERT INTO metadata (key, value) VALUES ('a', 'x')")
    database.execute("INSERT INTO metadata (key, value) VALUES ('b', 'y')")

    total = database.count("SELECT COUNT(*) AS total FROM metadata WHERE value = ?", ("x",))

    assert total == 1


def test_count_on_an_empty_table_is_zero(database: SqliteDatabase) -> None:
    assert database.count("SELECT COUNT(*) AS total FROM documents") == 0


# --------------------------------------------------------------------------- #
# Threading
# --------------------------------------------------------------------------- #
def test_each_thread_gets_its_own_connection(database: SqliteDatabase) -> None:
    main_connection = database.connect()
    seen: list[int] = []

    def worker() -> None:
        seen.append(id(database.connect()))
        database.close()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert seen and seen[0] != id(main_connection)


def test_concurrent_writers_both_succeed(database: SqliteDatabase) -> None:
    failures: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            for index in range(10):
                database.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)", (f"{name}-{index}", "x")
                )
        except BaseException as exc:  # pragma: no cover - only on a real failure
            failures.append(exc)
        finally:
            database.close()

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    row = database.fetch_one("SELECT COUNT(*) AS total FROM metadata WHERE value = 'x'")
    assert row is not None
    assert row["total"] == 20


def test_close_is_safe_to_call_twice(database: SqliteDatabase) -> None:
    database.connect()
    database.close()
    database.close()

    assert database.fetch_one("SELECT 1 AS value") is not None
