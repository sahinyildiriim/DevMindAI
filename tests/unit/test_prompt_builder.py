"""Unit tests for :mod:`devmind.application.prompt_builder`."""

from __future__ import annotations

import pytest

from devmind.application.dto import SearchResult
from devmind.application.prompt_builder import NO_CONTEXT_ANSWER, PromptBuilder
from devmind.domain.value_objects import ChunkId
from tests.factories import CHECKSUM, make_chunk, make_metadata

_ROUTING_METADATA = make_metadata(title="ASP.NET Core Routing")
_MIDDLEWARE_METADATA = make_metadata(title="Middleware Pipeline")


def _result(content: str, index: int, score: float, metadata: object) -> SearchResult:
    return SearchResult(
        chunk=make_chunk(
            chunk_id=ChunkId.for_document(CHECKSUM, index),
            content=content,
            index=index,
            start_offset=0,
            end_offset=len(content),
            metadata=metadata,
        ),
        score=score,
    )


RESULTS = (
    _result("Endpoint routing matches requests.", 0, 0.91, _ROUTING_METADATA),
    _result("Middleware runs in registration order.", 1, 0.62, _MIDDLEWARE_METADATA),
)


def test_the_system_prompt_forbids_outside_knowledge() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    assert "ONLY" in prompt.system
    assert "outside knowledge" in prompt.system


def test_the_system_prompt_carries_the_exact_refusal_sentence() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    assert NO_CONTEXT_ANSWER in prompt.system


def test_the_user_message_contains_the_question() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    assert "How does routing work?" in prompt.user


def test_the_user_message_contains_every_excerpt() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    assert "Endpoint routing matches requests." in prompt.user
    assert "Middleware runs in registration order." in prompt.user


def test_excerpts_are_numbered_in_the_given_order() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    assert prompt.user.index("[1]") < prompt.user.index("Endpoint routing")
    assert prompt.user.index("[2]") < prompt.user.index("Middleware runs")
    assert prompt.user.index("[1]") < prompt.user.index("[2]")


def test_each_excerpt_names_its_source_document() -> None:
    prompt = PromptBuilder().build("How does routing work?", RESULTS)

    for result in RESULTS:
        assert result.chunk.metadata.display_title in prompt.user


def test_building_without_any_result_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one retrieved chunk"):
        PromptBuilder().build("How does routing work?", ())
