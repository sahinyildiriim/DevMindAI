"""The single entry point for asking a grounded question.

This is the composition root for the chat feature: it wires the
concrete SQLite repositories and Foundry Local adapters behind
:class:`~devmind.application.use_cases.answer_query.AnswerQueryUseCase`,
so a caller - the future Streamlit UI, a CLI, or a test - never needs to
construct a database connection, a repository or a provider itself.
Composing across every layer this way is exactly what an outermost-ring
composition root is for; the orchestration it performs is a single
delegation, not business logic, which stays in ``AnswerQueryUseCase``.
"""

from __future__ import annotations

from devmind.application.dto.generated_answer import GeneratedAnswer
from devmind.application.prompt_builder import PromptBuilder
from devmind.application.use_cases.answer_query import AnswerQueryUseCase
from devmind.application.use_cases.search_chunks import SearchChunksUseCase
from devmind.core.config import Settings, get_settings
from devmind.core.logger import get_logger
from devmind.infrastructure.embeddings import build_embedding_provider
from devmind.infrastructure.llm import build_chat_provider
from devmind.infrastructure.persistence import (
    SqliteChunkRepository,
    SqliteDatabase,
    SqliteEmbeddingRepository,
    build_database,
)

__all__ = ["ChatService", "build_chat_service"]

_logger = get_logger(__name__)


class ChatService:
    """Answers a question from the indexed documentation, end to end.

    Takes the question, calls retrieval, builds the grounded prompt,
    sends it to the local chat model and returns the answer together
    with the sources it cites - the six steps this class exists to make
    reachable through one call, all of which
    :class:`~devmind.application.use_cases.answer_query.AnswerQueryUseCase`
    already implements as testable business logic.
    """

    def __init__(self, answer_use_case: AnswerQueryUseCase, database: SqliteDatabase) -> None:
        """Initialise the service.

        Args:
            answer_use_case: Fully wired use case that answers a query.
            database: Knowledge base connection this service owns and
                is responsible for closing.
        """
        self._answer_use_case = answer_use_case
        self._database = database

    def ask(
        self, question: str, *, top_k: int | None = None, min_score: float | None = None
    ) -> GeneratedAnswer:
        """Answer ``question`` using only the indexed documentation.

        Args:
            question: The user's natural language question.
            top_k: Maximum number of chunks to ground the answer in.
                Defaults to the configured retrieval setting.
            min_score: Minimum confidence a chunk must reach to be used.
                Defaults to the configured retrieval setting.

        Returns:
            The generated answer and the chunks it cites - empty when
            nothing relevant is indexed.

        Raises:
            ValueError: If the question is blank, or if ``top_k`` or
                ``min_score`` are supplied but out of range.
            EmbeddingError: If the question cannot be embedded.
            GenerationError: If the chat model cannot produce an answer.
            StorageError: If the knowledge base cannot be read.
        """
        answer = self._answer_use_case.execute(question, top_k=top_k, min_score=min_score)
        if answer.is_grounded:
            _logger.info("Answer grounded in: %s", self._describe(answer))
        return answer

    def close(self) -> None:
        """Release the knowledge base connection held by this service."""
        self._database.close()

    @staticmethod
    def _describe(answer: GeneratedAnswer) -> str:
        """Render the cited sources as a short, human readable summary.

        Args:
            answer: A grounded answer, i.e. one with at least one
                citation.

        Returns:
            The cited document titles and their confidence, in citation
            order.
        """
        return ", ".join(
            f"'{result.chunk.metadata.display_title}' ({result.score:.2f})"
            for result in answer.citations
        )


def build_chat_service(settings: Settings | None = None) -> ChatService:
    """Wire the chat pipeline from the active configuration.

    Args:
        settings: Application settings to apply. Defaults to the active
            settings.

    Returns:
        A service ready to answer questions. Call :meth:`ChatService.close`
        once it is no longer needed.

    Raises:
        StorageError: If the knowledge base cannot be opened.
    """
    resolved = settings if settings is not None else get_settings()
    database = build_database(resolved.database)
    search = SearchChunksUseCase(
        chunks=SqliteChunkRepository(database),
        embeddings=SqliteEmbeddingRepository(database),
        provider=build_embedding_provider(resolved.foundry),
        retrieval=resolved.retrieval,
    )
    answer_use_case = AnswerQueryUseCase(
        search=search,
        chat=build_chat_provider(resolved.foundry),
        prompt_builder=PromptBuilder(),
    )
    return ChatService(answer_use_case=answer_use_case, database=database)
