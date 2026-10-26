from types import SimpleNamespace

import httpx2
import openai
import pytest
from pydantic import BaseModel

from eventai.config import Settings
from eventai.llm import (
    DailyLimitReached,
    InvalidOutput,
    ProviderError,
    build_providers,
    complete_json,
)


class Pair(BaseModel):
    city: str
    seats: int


QUESTION = [{"role": "user", "content": "Where?"}]
GOOD = '{"city": "Leeds", "seats": 120}'


def test_primary_provider_answers(fake_provider):
    groq, groq_calls = fake_provider("groq", [GOOD])
    router, router_calls = fake_provider("openrouter", [])

    result = complete_json(QUESTION, Pair, providers=[groq, router])

    assert result == Pair(city="Leeds", seats=120)
    assert len(groq_calls.calls) == 1
    assert router_calls.calls == []


def test_rate_limit_falls_back_to_next_provider(fake_provider, rate_limit):
    groq, groq_calls = fake_provider("groq", [rate_limit()])
    router, router_calls = fake_provider("openrouter", [GOOD])

    result = complete_json(QUESTION, Pair, providers=[groq, router])

    assert result.city == "Leeds"
    assert router_calls.calls[0]["model"] == "openrouter-model"
    # The fallback gets the same request.
    assert router_calls.calls[0]["messages"] == groq_calls.calls[0]["messages"]


def test_all_providers_rate_limited(fake_provider, rate_limit):
    groq, _ = fake_provider("groq", [rate_limit()])
    router, _ = fake_provider("openrouter", [rate_limit()])

    with pytest.raises(DailyLimitReached):
        complete_json(QUESTION, Pair, providers=[groq, router])


def connection_error():
    return openai.APIConnectionError(request=httpx2.Request("POST", "http://test"))


def test_connection_error_falls_back_to_next_provider(fake_provider):
    groq, _ = fake_provider("groq", [connection_error()])
    router, router_calls = fake_provider("openrouter", [GOOD])

    assert complete_json(QUESTION, Pair, providers=[groq, router]).city == "Leeds"
    assert len(router_calls.calls) == 1


def test_connection_error_everywhere_is_not_a_limit(fake_provider, rate_limit):
    groq, _ = fake_provider("groq", [connection_error()])
    router, _ = fake_provider("openrouter", [rate_limit()])

    with pytest.raises(openai.APIConnectionError):
        complete_json(QUESTION, Pair, providers=[groq, router])


def test_empty_response_falls_back_then_raises(fake_provider):
    empty = SimpleNamespace(choices=None, error={"message": "Provider returned error"})
    groq, _ = fake_provider("groq", [GOOD])
    router, _ = fake_provider("openrouter", [empty])

    assert complete_json(QUESTION, Pair, providers=[router, groq]).city == "Leeds"
    with pytest.raises(ProviderError, match="Provider returned error"):
        complete_json(QUESTION, Pair, providers=[fake_provider("openrouter", [empty])[0]])


def test_invalid_output_is_retried_once(fake_provider):
    groq, calls = fake_provider("groq", ['{"city": "Leeds"}', GOOD])

    result = complete_json(QUESTION, Pair, providers=[groq])

    assert result.seats == 120
    assert len(calls.calls) == 2
    retry_messages = calls.calls[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"city": "Leeds"}'}
    assert "not valid" in retry_messages[-1]["content"]


def test_invalid_output_twice_raises(fake_provider):
    groq, _ = fake_provider("groq", ["not json", '{"seats": "many"}'])

    with pytest.raises(InvalidOutput):
        complete_json(QUESTION, Pair, providers=[groq])


def test_request_uses_temperature_zero_json_mode_and_schema(fake_provider):
    groq, calls = fake_provider("groq", [GOOD])

    complete_json(QUESTION, Pair, providers=[groq])

    call = calls.calls[0]
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0]["role"] == "system"
    assert '"seats"' in call["messages"][0]["content"]
    assert call["messages"][1:] == QUESTION


def test_fenced_json_is_accepted(fake_provider):
    groq, _ = fake_provider("groq", ["```json\n" + GOOD + "\n```"])

    assert complete_json(QUESTION, Pair, providers=[groq]).city == "Leeds"


def test_no_provider_raises():
    with pytest.raises(RuntimeError):
        complete_json(QUESTION, Pair, providers=[])


def test_build_providers_skips_missing_keys():
    assert build_providers(Settings()) == []

    only_router = build_providers(Settings(openrouter_api_key="k"))
    assert [p.name for p in only_router] == ["openrouter"]

    both = build_providers(Settings(groq_api_key="g", openrouter_api_key="k"))
    assert [p.name for p in both] == ["groq", "openrouter"]
    assert both[0].model == "openai/gpt-oss-120b"
    assert both[0].client.max_retries == 0
