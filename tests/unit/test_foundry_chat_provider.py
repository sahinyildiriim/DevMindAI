"""Unit tests for the Foundry Local chat completion adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
import pytest

from devmind.application.dto import Prompt
from devmind.domain.exceptions import GenerationError
from devmind.infrastructure.llm import FoundryChatProvider

BASE_URL = "http://localhost:5273/v1"
PROMPT = Prompt(system="Answer only from the excerpts.", user="Excerpts:\n...\n\nQuestion: How?")


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


@dataclass
class FakeCompletions:
    responder: Callable[[str, list[dict[str, str]]], FakeResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, *, model: str, messages: list[dict[str, str]], **kwargs: Any) -> FakeResponse:
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return self.responder(model, messages)


@dataclass
class FakeChat:
    completions: FakeCompletions


class FakeClient:
    """Stands in for the OpenAI client the adapter talks through."""

    base_url = BASE_URL

    def __init__(
        self, responder: Callable[[str, list[dict[str, str]]], FakeResponse] | None = None
    ) -> None:
        self.chat = FakeChat(FakeCompletions(responder or _echo_answer))


def _echo_answer(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
    return FakeResponse(
        choices=[FakeChoice(message=FakeMessage(content="Routing matches requests."))]
    )


def make_provider(
    client: Any,
    *,
    max_tokens: int = 512,
    temperature: float = 0.1,
    disable_thinking: bool = False,
) -> FoundryChatProvider:
    return FoundryChatProvider(
        client=client,
        model="phi-3.5-mini",
        max_tokens=max_tokens,
        temperature=temperature,
        disable_thinking=disable_thinking,
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_the_answer_text_is_returned_stripped() -> None:
    def padded(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        return FakeResponse(choices=[FakeChoice(message=FakeMessage(content="  Answer.  \n"))])

    assert make_provider(FakeClient(padded)).complete(PROMPT) == "Answer."


def test_the_system_and_user_prompt_are_sent_as_separate_messages() -> None:
    client = FakeClient()

    make_provider(client).complete(PROMPT)

    sent = client.chat.completions.calls[0]["messages"]
    assert sent == [
        {"role": "system", "content": PROMPT.system},
        {"role": "user", "content": PROMPT.user},
    ]


def test_max_tokens_and_temperature_are_forwarded() -> None:
    client = FakeClient()

    make_provider(client, max_tokens=256, temperature=0.4).complete(PROMPT)

    call = client.chat.completions.calls[0]
    assert call["max_tokens"] == 256
    assert call["temperature"] == 0.4


def test_the_configured_model_is_requested() -> None:
    client = FakeClient()

    make_provider(client).complete(PROMPT)

    assert client.chat.completions.calls[0]["model"] == "phi-3.5-mini"


def test_thinking_is_left_untouched_by_default() -> None:
    client = FakeClient()

    make_provider(client).complete(PROMPT)

    sent = client.chat.completions.calls[0]["messages"]
    assert sent[1] == {"role": "user", "content": PROMPT.user}


def test_disabling_thinking_appends_the_qwen3_no_think_directive() -> None:
    client = FakeClient()

    make_provider(client, disable_thinking=True).complete(PROMPT)

    sent = client.chat.completions.calls[0]["messages"]
    assert sent[1] == {"role": "user", "content": f"{PROMPT.user} /no_think"}
    # The system prompt is untouched - only the user turn carries the directive.
    assert sent[0] == {"role": "system", "content": PROMPT.system}


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def test_an_unreachable_service_is_explained() -> None:
    def refuse(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        raise openai.APIConnectionError(
            request=httpx.Request("POST", f"{BASE_URL}/chat/completions")
        )

    with pytest.raises(GenerationError, match="foundry service start"):
        make_provider(FakeClient(refuse)).complete(PROMPT)


def test_the_endpoint_is_named_when_the_service_is_unreachable() -> None:
    def refuse(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        raise openai.APIConnectionError(
            request=httpx.Request("POST", f"{BASE_URL}/chat/completions")
        )

    with pytest.raises(GenerationError, match="localhost:5273"):
        make_provider(FakeClient(refuse)).complete(PROMPT)


def test_other_client_failures_are_wrapped() -> None:
    def fail(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        raise openai.OpenAIError("the model is not loaded")

    with pytest.raises(GenerationError, match="the model is not loaded"):
        make_provider(FakeClient(fail)).complete(PROMPT)


def test_a_reply_with_no_choices_is_refused() -> None:
    def empty(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        return FakeResponse(choices=[])

    with pytest.raises(GenerationError, match="returned no choices"):
        make_provider(FakeClient(empty)).complete(PROMPT)


@pytest.mark.parametrize("content", [None, "", "   "])
def test_a_blank_or_missing_answer_is_refused(content: str | None) -> None:
    def blank(_model: str, _messages: list[dict[str, str]]) -> FakeResponse:
        return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=content))])

    with pytest.raises(GenerationError, match="empty response"):
        make_provider(FakeClient(blank)).complete(PROMPT)


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("model", "max_tokens", "temperature", "message"),
    [
        ("", 512, 0.1, "model must not be empty"),
        ("   ", 512, 0.1, "model must not be empty"),
        ("phi-3.5-mini", 0, 0.1, "Max tokens"),
        ("phi-3.5-mini", -1, 0.1, "Max tokens"),
        ("phi-3.5-mini", 512, -0.1, "Temperature"),
        ("phi-3.5-mini", 512, 2.1, "Temperature"),
    ],
)
def test_invalid_settings_are_rejected(
    model: str, max_tokens: int, temperature: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        FoundryChatProvider(
            client=FakeClient(), model=model, max_tokens=max_tokens, temperature=temperature
        )
