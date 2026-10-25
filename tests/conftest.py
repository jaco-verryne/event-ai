from types import SimpleNamespace

import httpx2
import openai
import pytest

from eventai.llm import Provider


class FakeCompletions:
    """Returns the next output from a list, or raises it when it is an exception."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


@pytest.fixture
def fake_provider():
    """Factory: fake_provider(name, outputs) -> (Provider, FakeCompletions)."""

    def make(name, outputs):
        completions = FakeCompletions(outputs)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        return Provider(name, client, f"{name}-model"), completions

    return make


@pytest.fixture
def rate_limit():
    def make():
        response = httpx2.Response(429, request=httpx2.Request("POST", "http://test"))
        return openai.RateLimitError("rate limit", response=response, body=None)

    return make
