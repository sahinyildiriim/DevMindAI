"""Unit tests for the SQLite document repository."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from devmind.domain.value_objects import DocumentFormat
from devmind.infrastructure.persistence import SqliteDatabase, SqliteDocumentRepository
from tests.factories import make_metadata


@pytest.fixture
def repository(database: SqliteDatabase) -> SqliteDocumentRepository:
    return SqliteDocumentRepository(database)


def test_a_saved_document_is_read_back_unchanged(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    metadata = make_metadata(
        source_path=tmp_path / "routing.pdf",
        document_format=DocumentFormat.PDF,
        size_bytes=4096,
        title="ASP.NET Core Routing",
        author="Microsoft Learn",
        page_count=12,
    )

    repository.save(metadata)

    assert repository.get(tmp_path / "routing.pdf") == metadata


def test_absent_optional_fields_survive_the_round_trip(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    metadata = make_metadata(source_path=tmp_path / "notes.txt")

    repository.save(metadata)
    stored = repository.get(tmp_path / "notes.txt")

    assert stored is not None
    assert stored.title is None
    assert stored.author is None
    assert stored.page_count is None


def test_the_modification_time_keeps_its_time_zone(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    moment = datetime(2026, 3, 1, 8, 30, 15, tzinfo=UTC)
    repository.save(make_metadata(source_path=tmp_path / "a.md", modified_at=moment))

    stored = repository.get(tmp_path / "a.md")

    assert stored is not None
    assert stored.modified_at == moment


def test_unknown_paths_read_as_none(repository: SqliteDocumentRepository, tmp_path: Path) -> None:
    assert repository.get(tmp_path / "never-indexed.md") is None


def test_saving_the_same_path_updates_the_existing_record(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    source = tmp_path / "guide.md"
    repository.save(make_metadata(source_path=source, checksum="a" * 64, size_bytes=100))
    repository.save(
        make_metadata(source_path=source, checksum="b" * 64, size_bytes=200, title="Rewritten")
    )

    stored = repository.get(source)

    assert repository.count() == 1
    assert stored is not None
    assert stored.checksum == "b" * 64
    assert stored.size_bytes == 200
    assert stored.title == "Rewritten"


def test_documents_are_listed_in_path_order(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    for name in ("c.md", "a.md", "b.md"):
        repository.save(make_metadata(source_path=tmp_path / name))

    listed = repository.list_all()

    assert [metadata.file_name for metadata in listed] == ["a.md", "b.md", "c.md"]


def test_deleting_reports_whether_anything_was_removed(
    repository: SqliteDocumentRepository, tmp_path: Path
) -> None:
    source = tmp_path / "guide.md"
    repository.save(make_metadata(source_path=source))

    assert repository.delete(source) is True
    assert repository.delete(source) is False
    assert repository.get(source) is None


def test_counting_an_empty_knowledge_base(repository: SqliteDocumentRepository) -> None:
    assert repository.count() == 0
    assert repository.list_all() == ()
