"""End-to-end integration tests: index, embed, search and answer together.

Every layer is real - parsing, chunking, SQLite persistence, retrieval
and answer generation - except the two Foundry Local adapters, replaced
by deterministic fakes. What is being verified here is that these real
components compose correctly through actual storage: that a document
indexed through one connection is embedded, found and cited correctly
through another, and that re-indexing and the "no context" guarantee
hold across the whole chain. Each piece's own behaviour in isolation is
already covered under ``tests/unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.application.prompt_builder import NO_CONTEXT_ANSWER
from tests.integration.factories import (
    EchoChatProvider,
    TopicEmbeddingProvider,
    build_chat_service_for_test,
    build_knowledge_base_service_for_test,
)

ROUTING_DOC = (
    "# Endpoint Routing\n\n"
    "Endpoint routing matches an incoming request to an endpoint. Routing "
    "middleware examines the request path and dispatches it to the "
    "endpoint registered for that route.\n"
)
DI_DOC = (
    "# Dependency Injection\n\n"
    "Dependency injection resolves a service from the container instead "
    "of the class constructing it directly. Registering a service with "
    "the container lets the framework manage its lifetime.\n"
)
ARCHITECTURE_DOC = (
    "# Clean Architecture\n\n"
    "Clean architecture separates the domain layer from frameworks and "
    "storage. Each layer depends only on the layers beneath it.\n"
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "devmind.db"


@pytest.fixture
def documents_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "documents"
    directory.mkdir()
    return directory


def write(directory: Path, name: str, content: str) -> Path:
    """Write a fixture document to disk and return its path."""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Indexing, embedding and finding a document again
# --------------------------------------------------------------------------- #
def test_an_indexed_document_is_findable_and_cited(db_path: Path, documents_dir: Path) -> None:
    embedding_provider = TopicEmbeddingProvider()
    kb_service = build_knowledge_base_service_for_test(db_path, embedding_provider)
    chat_service = build_chat_service_for_test(
        db_path, embedding_provider, EchoChatProvider("Routing matches a request to an endpoint.")
    )
    try:
        kb_service.index_document(write(documents_dir, "routing.md", ROUTING_DOC))
        kb_service.embed_pending()

        answer = chat_service.ask("How does endpoint routing work?")

        assert answer.is_grounded is True
        assert answer.text == "Routing matches a request to an endpoint."
        assert answer.citations[0].chunk.metadata.file_name == "routing.md"
        assert answer.citations[0].score > 0.0
    finally:
        kb_service.close()
        chat_service.close()


def test_search_distinguishes_between_unrelated_documents(
    db_path: Path, documents_dir: Path
) -> None:
    embedding_provider = TopicEmbeddingProvider()
    kb_service = build_knowledge_base_service_for_test(db_path, embedding_provider)
    chat_service = build_chat_service_for_test(db_path, embedding_provider, EchoChatProvider())
    try:
        kb_service.index_document(write(documents_dir, "routing.md", ROUTING_DOC))
        kb_service.index_document(write(documents_dir, "di.md", DI_DOC))
        kb_service.index_document(write(documents_dir, "architecture.md", ARCHITECTURE_DOC))
        kb_service.embed_pending()

        routing_answer = chat_service.ask("How does routing dispatch a request?")
        di_answer = chat_service.ask("How does the container resolve a service?")

        assert routing_answer.citations[0].chunk.metadata.file_name == "routing.md"
        assert di_answer.citations[0].chunk.metadata.file_name == "di.md"
    finally:
        kb_service.close()
        chat_service.close()


def test_knowledge_base_stats_reflect_the_indexed_and_embedded_state(
    db_path: Path, documents_dir: Path
) -> None:
    embedding_provider = TopicEmbeddingProvider()
    kb_service = build_knowledge_base_service_for_test(db_path, embedding_provider)
    try:
        kb_service.index_document(write(documents_dir, "routing.md", ROUTING_DOC))
        kb_service.index_document(write(documents_dir, "di.md", DI_DOC))
        before_embedding = kb_service.get_stats()

        kb_service.embed_pending()
        after_embedding = kb_service.get_stats()

        assert before_embedding.document_count == 2
        assert before_embedding.pending_embedding_count == before_embedding.chunk_count
        assert after_embedding.pending_embedding_count == 0
        assert after_embedding.is_embedding_model_current is True
        assert {metadata.file_name for metadata in kb_service.list_documents()} == {
            "routing.md",
            "di.md",
        }
    finally:
        kb_service.close()


# --------------------------------------------------------------------------- #
# Re-indexing lifecycle
# --------------------------------------------------------------------------- #
def test_reindexing_unchanged_content_leaves_search_and_stats_untouched(
    db_path: Path, documents_dir: Path
) -> None:
    embedding_provider = TopicEmbeddingProvider()
    kb_service = build_knowledge_base_service_for_test(db_path, embedding_provider)
    chat_service = build_chat_service_for_test(db_path, embedding_provider, EchoChatProvider())
    try:
        source = write(documents_dir, "routing.md", ROUTING_DOC)
        kb_service.index_document(source)
        kb_service.embed_pending()

        result = kb_service.index_document(source)

        assert result.was_skipped is True
        assert kb_service.get_stats().pending_embedding_count == 0
        assert chat_service.ask("How does routing work?").is_grounded is True
    finally:
        kb_service.close()
        chat_service.close()


def test_reindexing_changed_content_updates_what_search_finds(
    db_path: Path, documents_dir: Path
) -> None:
    embedding_provider = TopicEmbeddingProvider()
    kb_service = build_knowledge_base_service_for_test(db_path, embedding_provider)
    chat_service = build_chat_service_for_test(db_path, embedding_provider, EchoChatProvider())
    try:
        source = write(documents_dir, "notes.md", ROUTING_DOC)
        kb_service.index_document(source)
        kb_service.embed_pending()

        write(documents_dir, "notes.md", DI_DOC)
        result = kb_service.index_document(source)
        kb_service.embed_pending()

        assert result.was_skipped is False
        di_answer = chat_service.ask("How does the container resolve a service?")
        assert di_answer.citations[0].chunk.metadata.file_name == "notes.md"
        assert "container" in di_answer.citations[0].chunk.content.lower()
    finally:
        kb_service.close()
        chat_service.close()


# --------------------------------------------------------------------------- #
# No context: the hard gate must hold across the real pipeline
# --------------------------------------------------------------------------- #
def test_an_empty_knowledge_base_refuses_without_calling_the_chat_model(db_path: Path) -> None:
    embedding_provider = TopicEmbeddingProvider()
    chat = EchoChatProvider()
    chat_service = build_chat_service_for_test(db_path, embedding_provider, chat)
    try:
        answer = chat_service.ask("Anything at all")

        assert answer.text == NO_CONTEXT_ANSWER
        assert answer.citations == ()
        assert chat.received_prompts == []
    finally:
        chat_service.close()
