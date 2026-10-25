"""One OpenAI-compatible client for all LLM calls: Groq first, OpenRouter on a rate limit (D2)."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from eventai.config import Settings, load_settings

log = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 60

T = TypeVar("T", bound=BaseModel)


class DailyLimitReached(Exception):
    """Each provider returned HTTP 429. The UI shows the free-limit message."""


class InvalidOutput(Exception):
    """The model gave output that failed the schema twice."""


@dataclass(frozen=True)
class Provider:
    name: str
    client: Any  # openai.OpenAI, or a fake in the tests
    model: str


def build_providers(settings: Settings) -> list[Provider]:
    providers = []
    if settings.groq_api_key:
        # No SDK retries: a 429 must go to the fallback at once, not wait on back-off.
        client = openai.OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=settings.groq_api_key,
            max_retries=0,
            timeout=TIMEOUT_SECONDS,
        )
        providers.append(Provider("groq", client, settings.groq_model))
    if settings.openrouter_api_key and settings.openrouter_model:
        client = openai.OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            timeout=TIMEOUT_SECONDS,
        )
        providers.append(Provider("openrouter", client, settings.openrouter_model))
    return providers


@lru_cache
def _default_providers() -> tuple[Provider, ...]:
    return tuple(build_providers(load_settings()))


def complete_json(
    messages: list[dict[str, str]],
    schema: type[T],
    providers: Sequence[Provider] | None = None,
) -> T:
    """Return the model reply as a validated `schema` object. Retry once on invalid output."""
    providers = list(providers if providers is not None else _default_providers())
    if not providers:
        raise RuntimeError("No LLM provider. Set GROQ_API_KEY or OPENROUTER_API_KEY.")

    messages = [_schema_message(schema), *messages]
    content = _chat(messages, providers)
    try:
        return schema.model_validate_json(_strip_fences(content))
    except ValidationError as err:
        log.warning("Invalid LLM output, retrying once: %s", err)
        messages = [
            *messages,
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": f"Your JSON is not valid:\n{err}\nReply again with one valid JSON object only.",
            },
        ]

    content = _chat(messages, providers)
    try:
        return schema.model_validate_json(_strip_fences(content))
    except ValidationError as err:
        raise InvalidOutput(str(err)) from err


def _chat(messages: list[dict[str, str]], providers: Sequence[Provider]) -> str:
    for provider in providers:
        try:
            response = provider.client.chat.completions.create(
                model=provider.model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except openai.RateLimitError:
            log.warning("%s returned a rate-limit error, trying the next provider", provider.name)
            continue
        log.info("LLM call served by %s (%s)", provider.name, provider.model)
        return response.choices[0].message.content or ""
    raise DailyLimitReached("Each LLM provider returned a rate-limit error.")


def _schema_message(schema: type[BaseModel]) -> dict[str, str]:
    return {
        "role": "system",
        "content": "Reply with one JSON object only. It must match this JSON schema:\n"
        + json.dumps(schema.model_json_schema()),
    }


def _strip_fences(content: str) -> str:
    # Some free models wrap JSON in ``` fences, even in JSON mode.
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
