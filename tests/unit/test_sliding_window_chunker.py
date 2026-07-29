"""Unit tests for the sliding window chunking engine."""

from __future__ import annotations

from itertools import pairwise

import pytest

from devmind.core.config import RetrievalConfig
from devmind.domain.entities import DocumentChunk
from devmind.infrastructure.chunking import SlidingWindowChunker, build_chunker
from tests.factories import CHECKSUM, make_document

PROSE = (
    "Endpoint routing matches incoming requests to endpoints. "
    "Middleware components run in the order they are registered. "
    "Dependency injection resolves services from the container. "
    "Configuration providers are layered on top of each other. "
    "Hosted services run background work for the application. "
    "Logging providers write to the configured destinations. "
)

# Parsers always hand over normalised text, so the fixtures are stripped
# exactly like real documents are.
LONG_TEXT = (PROSE * 3).strip()


def assert_offsets_describe_the_source(chunks: tuple[DocumentChunk, ...], text: str) -> None:
    """Every chunk must be reproducible by slicing the document text."""
    for chunk in chunks:
        assert text[chunk.start_offset : chunk.end_offset] == chunk.content


# --------------------------------------------------------------------------- #
# Sizing and overlap
# --------------------------------------------------------------------------- #
def test_short_document_yields_a_single_chunk() -> None:
    document = make_document("A short note about routing.")

    chunks = SlidingWindowChunker(chunk_size=200, chunk_overlap=50).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].content == document.content
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(document.content)


def test_long_document_is_split_into_bounded_chunks() -> None:
    document = make_document((PROSE * 4).strip())

    chunks = SlidingWindowChunker(chunk_size=120, chunk_overlap=20).chunk(document)

    assert len(chunks) > 1
    assert all(chunk.character_count <= 120 for chunk in chunks)


def test_consecutive_chunks_overlap() -> None:
    document = make_document(LONG_TEXT)

    chunks = SlidingWindowChunker(chunk_size=150, chunk_overlap=60).chunk(document)

    assert all(
        following.start_offset < current.end_offset for current, following in pairwise(chunks)
    )


def test_zero_overlap_produces_disjoint_chunks() -> None:
    document = make_document(LONG_TEXT)

    chunks = SlidingWindowChunker(chunk_size=150, chunk_overlap=0).chunk(document)

    assert all(
        following.start_offset >= current.end_offset for current, following in pairwise(chunks)
    )


def test_chunks_cover_the_whole_document_without_gaps() -> None:
    text = LONG_TEXT
    document = make_document(text)

    chunks = SlidingWindowChunker(chunk_size=140, chunk_overlap=30).chunk(document)

    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(text)
    assert all(
        following.start_offset <= current.end_offset for current, following in pairwise(chunks)
    )


# --------------------------------------------------------------------------- #
# Cut points
# --------------------------------------------------------------------------- #
def test_cut_prefers_a_paragraph_break() -> None:
    body = "A" * 45
    document = make_document(f"{body}\n\n{'B' * 200}")

    chunks = SlidingWindowChunker(chunk_size=50, chunk_overlap=0).chunk(document)

    assert chunks[0].content == body


def test_cut_prefers_a_sentence_end() -> None:
    body = "A" * 40
    document = make_document(f"{body}. {'B' * 200}")

    chunks = SlidingWindowChunker(chunk_size=50, chunk_overlap=0).chunk(document)

    assert chunks[0].content == f"{body}."


def test_cut_falls_back_to_a_word_boundary() -> None:
    document = make_document("alpha beta gamma delta epsilon zeta eta theta iota kappa")

    chunks = SlidingWindowChunker(chunk_size=20, chunk_overlap=0).chunk(document)

    assert not any(chunk.content.startswith(" ") or chunk.content.endswith(" ") for chunk in chunks)
    assert chunks[0].content == "alpha beta gamma"


def test_text_without_separators_is_cut_at_the_size_limit() -> None:
    text = "x" * 1000
    document = make_document(text)

    chunks = SlidingWindowChunker(chunk_size=100, chunk_overlap=0).chunk(document)

    assert len(chunks) == 10
    assert all(chunk.character_count == 100 for chunk in chunks)
    assert_offsets_describe_the_source(chunks, text)


def test_a_window_holding_only_whitespace_never_becomes_a_chunk() -> None:
    text = "\n" * 10 + "Routing basics"
    document = make_document(text)

    chunks = SlidingWindowChunker(chunk_size=6, chunk_overlap=0).chunk(document)

    assert chunks[0].start_offset == 10
    assert all(chunk.content == chunk.content.strip() for chunk in chunks)
    assert_offsets_describe_the_source(chunks, text)


def test_a_nearly_total_overlap_still_terminates() -> None:
    text = "y" * 200
    document = make_document(text)

    chunks = SlidingWindowChunker(chunk_size=100, chunk_overlap=99).chunk(document)

    assert chunks[-1].end_offset == len(text)
    assert all(chunk.character_count <= 100 for chunk in chunks)


# --------------------------------------------------------------------------- #
# Identity, ordering and metadata
# --------------------------------------------------------------------------- #
def test_chunks_are_indexed_in_reading_order() -> None:
    document = make_document(LONG_TEXT)

    chunks = SlidingWindowChunker(chunk_size=140, chunk_overlap=30).chunk(document)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(
        current.start_offset < following.start_offset for current, following in pairwise(chunks)
    )


def test_chunk_identifiers_are_unique_and_derived_from_the_document() -> None:
    document = make_document(LONG_TEXT)

    chunks = SlidingWindowChunker(chunk_size=140, chunk_overlap=30).chunk(document)

    identifiers = [chunk.chunk_id.value for chunk in chunks]
    assert len(set(identifiers)) == len(identifiers)
    assert all(identifier.startswith(CHECKSUM[:16]) for identifier in identifiers)


def test_chunking_the_same_document_twice_is_reproducible() -> None:
    document = make_document(LONG_TEXT)
    chunker = SlidingWindowChunker(chunk_size=140, chunk_overlap=30)

    assert chunker.chunk(document) == chunker.chunk(document)


def test_metadata_is_carried_into_every_chunk() -> None:
    document = make_document(LONG_TEXT, title="ASP.NET Core Routing", author="Microsoft Learn")

    chunks = SlidingWindowChunker(chunk_size=140, chunk_overlap=30).chunk(document)

    assert all(chunk.metadata == document.metadata for chunk in chunks)
    assert all(chunk.metadata.title == "ASP.NET Core Routing" for chunk in chunks)
    assert all(chunk.metadata.author == "Microsoft Learn" for chunk in chunks)


def test_offsets_always_describe_the_source_text() -> None:
    text = LONG_TEXT
    document = make_document(text)

    chunks = SlidingWindowChunker(chunk_size=140, chunk_overlap=30).chunk(document)

    assert_offsets_describe_the_source(chunks, text)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap", "message"),
    [
        (0, 0, "Chunk size"),
        (-1, 0, "Chunk size"),
        (100, -1, "Chunk overlap"),
        (100, 100, "Chunk overlap"),
        (100, 150, "Chunk overlap"),
    ],
)
def test_invalid_settings_are_rejected(chunk_size: int, chunk_overlap: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SlidingWindowChunker(chunk_size, chunk_overlap)


def test_build_chunker_honours_the_retrieval_settings() -> None:
    document = make_document("z" * 500)

    chunks = build_chunker(RetrievalConfig(chunk_size=100, chunk_overlap=0)).chunk(document)

    assert len(chunks) == 5
    assert all(chunk.character_count == 100 for chunk in chunks)
