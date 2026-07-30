"""Generate a grounded answer to a query, or refuse when there is none."""

from __future__ import annotations

from time import perf_counter

from devmind.application.dto.generated_answer import GeneratedAnswer
from devmind.application.interfaces.chat_provider import ChatProvider
from devmind.application.prompt_builder import NO_CONTEXT_ANSWER, PromptBuilder
from devmind.application.use_cases.search_chunks import SearchChunksUseCase
from devmind.core.logger import get_logger

__all__ = ["AnswerQueryUseCase"]

_logger = get_logger(__name__)


class AnswerQueryUseCase:
    """Answers a query from the indexed documentation, and nothing else.

    When retrieval finds no context at all, the fixed refusal is
    returned directly and the chat model is never called: no prompt
    wording can *guarantee* a model refuses to answer on its own, so
    this path does not depend on the model's cooperation. When context
    is found, the model is still instructed to refuse the same way if
    the excerpts turn out not to answer the question - a second,
    weaker line of defence for a case retrieval alone cannot detect.
    """

    def __init__(
        self,
        search: SearchChunksUseCase,
        chat: ChatProvider,
        prompt_builder: PromptBuilder,
    ) -> None:
        """Initialise the use case.

        Args:
            search: Finds the chunks relevant to the query.
            chat: Generates the answer from a grounded prompt.
            prompt_builder: Composes the grounded prompt.
        """
        self._search = search
        self._chat = chat
        self._prompt_builder = prompt_builder

    def execute(
        self, query: str, *, top_k: int | None = None, min_score: float | None = None
    ) -> GeneratedAnswer:
        """Answer ``query`` using only the indexed documentation.

        Args:
            query: Natural language question.
            top_k: Maximum number of chunks to ground the answer in.
                Defaults to the configured retrieval setting.
            min_score: Minimum confidence a chunk must reach to be used.
                Defaults to the configured retrieval setting.

        Returns:
            The generated answer and the chunks it cites. The fixed
            refusal, with no citations, when nothing relevant is
            indexed.

        Raises:
            ValueError: If the query is blank, or if ``top_k`` or
                ``min_score`` are supplied but out of range.
            EmbeddingError: If the query cannot be embedded.
            GenerationError: If the chat model cannot produce an answer.
            StorageError: If the knowledge base cannot be read.
        """
        results = self._search.execute(query, top_k=top_k, min_score=min_score)
        if not results:
            _logger.info("No indexed context for this query; returning the fixed refusal")
            return GeneratedAnswer(text=NO_CONTEXT_ANSWER, citations=())

        started_at = perf_counter()
        prompt = self._prompt_builder.build(query, results)
        text = self._chat.complete(prompt)

        _logger.info(
            "Generated an answer from %d citation(s) in %.3fs using '%s'",
            len(results),
            perf_counter() - started_at,
            self._chat.model,
        )
        return GeneratedAnswer(text=text, citations=results)
