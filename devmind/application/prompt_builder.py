"""Composes the grounded prompt sent to the chat model.

This is the application's only line of defence against the model
answering from anything but the retrieved documentation: the system
instruction forbids outside knowledge and prescribes the exact refusal
sentence, and the user message carries nothing but the retrieved
excerpts and the question. There is a second, stronger line of defence
in :class:`~devmind.application.use_cases.answer_query.AnswerQueryUseCase`,
which never calls the model at all when retrieval found no context - a
guarantee prompting alone cannot give, since a model can always ignore
its instructions.
"""

from __future__ import annotations

from typing import Final

from devmind.application.dto.prompt import Prompt
from devmind.application.dto.search_result import SearchResult

__all__ = ["NO_CONTEXT_ANSWER", "PromptBuilder"]

NO_CONTEXT_ANSWER: Final[str] = "I couldn't find enough information in the indexed documents."
"""Refusal used both as the hard-coded fallback and as the model's own
instructed reply, so the two paths can never disagree in wording."""

_SYSTEM_PROMPT: Final[str] = (
    "You are DevMind AI, a documentation assistant. Answer the user's question "
    "using ONLY the numbered excerpts provided in the user message. Do not use "
    "any outside knowledge, and do not guess or speculate beyond what the "
    "excerpts state.\n\n"
    f"If the excerpts do not contain enough information to answer, reply with "
    f'exactly this sentence and nothing else: "{NO_CONTEXT_ANSWER}"\n\n'
    "Otherwise, answer clearly and concisely, drawing only on the excerpts."
)


class PromptBuilder:
    """Turns a query and its retrieved chunks into a chat completion request."""

    def build(self, query: str, results: tuple[SearchResult, ...]) -> Prompt:
        """Compose the system and user parts of the request.

        Args:
            query: The user's question.
            results: The retrieved chunks to ground the answer in, most
                relevant first. Must not be empty: a query with no
                retrieved context is handled by the caller before a
                prompt is ever built, since no wording of a prompt can
                guarantee the model will refuse to answer on its own.

        Returns:
            The composed prompt.

        Raises:
            ValueError: If ``results`` is empty.
        """
        if not results:
            raise ValueError("Cannot build a grounded prompt without at least one retrieved chunk.")
        return Prompt(system=_SYSTEM_PROMPT, user=self._build_user_message(query, results))

    @staticmethod
    def _build_user_message(query: str, results: tuple[SearchResult, ...]) -> str:
        """Format the retrieved excerpts and the question.

        Args:
            query: The user's question.
            results: The retrieved chunks, most relevant first.

        Returns:
            The user message: numbered excerpts followed by the
            question.
        """
        excerpts = "\n\n".join(
            f"[{index}] Source: {result.chunk.metadata.display_title}\n{result.chunk.content}"
            for index, result in enumerate(results, start=1)
        )
        return f"Excerpts:\n\n{excerpts}\n\nQuestion: {query}"
