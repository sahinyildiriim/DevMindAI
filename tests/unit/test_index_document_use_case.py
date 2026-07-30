"""Unit tests for document indexing, against a real knowledge base."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.application.use_cases import IndexDocumentUseCase
from devmind.core.config import DocumentConfig, RetrievalConfig
from devmind.domain.exceptions import DocumentNotFoundError, UnsupportedFormatError
from devmind.infrastructure.chunking import build_chunker
from devmind.infrastructure.parsers import build_parser_registry
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteDocumentRepository,
)


def make_use_case(database: SqliteDatabase, *, max_file_size_mb: int = 25) -> IndexDocumentUseCase:
    return IndexDocumentUseCase(
        parsers=build_parser_registry(DocumentConfig(max_file_size_mb=max_file_size_mb)),
        chunker=build_chunker(RetrievalConfig(chunk_size=1000, chunk_overlap=100)),
        documents=SqliteDocumentRepository(database),
        chunks=SqliteChunkRepository(database),
    )


def test_indexing_a_new_document_stores_it_and_its_chunks(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text(
        "# Routing\n\nEndpoint routing matches incoming requests.\n", encoding="utf-8"
    )
    use_case = make_use_case(database)

    result = use_case.execute(source)

    assert result.was_skipped is False
    assert result.chunks_indexed == 1
    assert result.metadata.title == "Routing"
    assert SqliteDocumentRepository(database).count() == 1
    assert SqliteChunkRepository(database).count() == 1


def test_indexing_the_same_content_twice_is_skipped_the_second_time(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    use_case = make_use_case(database)

    first = use_case.execute(source)
    second = use_case.execute(source)

    assert first.was_skipped is False
    assert second.was_skipped is True
    assert second.chunks_indexed == 0
    assert SqliteDocumentRepository(database).count() == 1


def test_changed_content_at_the_same_path_is_re_indexed(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Endpoint routing matches incoming requests.\n", encoding="utf-8")
    use_case = make_use_case(database)
    use_case.execute(source)

    source.write_text(
        "Endpoint routing matches incoming requests, in registration order.\n", encoding="utf-8"
    )
    result = use_case.execute(source)

    assert result.was_skipped is False
    assert result.chunks_indexed == 1
    documents = SqliteDocumentRepository(database)
    assert documents.count() == 1
    assert documents.get(source).checksum == result.metadata.checksum


def test_replacing_the_content_replaces_its_chunks(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "routing.md"
    source.write_text("Short.\n", encoding="utf-8")
    use_case = make_use_case(database)
    use_case.execute(source)

    source.write_text(
        "A very different and considerably longer paragraph of text.\n", encoding="utf-8"
    )
    use_case.execute(source)

    chunks = SqliteChunkRepository(database)
    stored = chunks.list_for_document(source)
    assert len(stored) == 1
    assert "considerably longer" in stored[0].content


def test_indexing_a_missing_file_is_reported(database: SqliteDatabase, tmp_path: Path) -> None:
    use_case = make_use_case(database)

    with pytest.raises(DocumentNotFoundError):
        use_case.execute(tmp_path / "absent.md")


def test_indexing_an_unsupported_format_is_reported(
    database: SqliteDatabase, tmp_path: Path
) -> None:
    source = tmp_path / "notes.xyz"
    source.write_text("content", encoding="utf-8")
    use_case = make_use_case(database)

    with pytest.raises(UnsupportedFormatError):
        use_case.execute(source)
