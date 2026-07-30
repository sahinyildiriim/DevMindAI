"""Chat page: ask a question, see the grounded answer and its sources."""

from __future__ import annotations

import streamlit as st

from devmind.application.dto import GeneratedAnswer
from devmind.core.exceptions import DevMindError
from devmind.presentation.ui.services import get_chat_service

__all__ = ["render"]

_HISTORY_KEY = "devmind_chat_history"
_SOURCE_PREVIEW_LENGTH = 280

_Turn = tuple[str, GeneratedAnswer | None, str | None]


def render() -> None:
    """Render the Chat page."""
    st.title("💬 Chat")
    st.caption("Ask a question. Answers are grounded only in the indexed documentation.")

    history: list[_Turn] = st.session_state.setdefault(_HISTORY_KEY, [])
    for past_question, past_answer, past_error in history:
        _render_turn(past_question, past_answer, past_error)

    new_question = st.chat_input("Ask a question about the indexed documentation")
    if not new_question:
        return

    new_answer, new_error = _ask(new_question)
    _render_turn(new_question, new_answer, new_error)
    history.append((new_question, new_answer, new_error))


def _ask(question: str) -> tuple[GeneratedAnswer | None, str | None]:
    """Ask the Chat Service, turning a domain failure into a message.

    Args:
        question: The user's question.

    Returns:
        The answer and ``None`` on success, or ``None`` and an error
        message on failure.
    """
    try:
        with st.spinner("Thinking..."):
            return get_chat_service().ask(question), None
    except (DevMindError, ValueError) as exc:
        return None, str(exc)


def _render_turn(question: str, answer: GeneratedAnswer | None, error: str | None) -> None:
    """Render one question and its answer or error.

    Args:
        question: The question that was asked.
        answer: The generated answer, when the call succeeded.
        error: The error message, when the call failed.
    """
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        if error is not None:
            st.error(error)
        elif answer is not None:
            _render_answer(answer)


def _render_answer(answer: GeneratedAnswer) -> None:
    """Render an answer's text and, when grounded, its cited sources.

    Args:
        answer: The answer to render.
    """
    st.write(answer.text)
    if not answer.is_grounded:
        return

    with st.expander(f"Sources ({len(answer.citations)})"):
        for result in answer.citations:
            content = result.chunk.content
            preview = content[:_SOURCE_PREVIEW_LENGTH]
            if len(content) > _SOURCE_PREVIEW_LENGTH:
                preview += "…"
            st.markdown(
                f"**{result.chunk.metadata.display_title}** — confidence: {result.score:.0%}"
            )
            st.caption(preview)
