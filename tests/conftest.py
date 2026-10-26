import hashlib
import math
import os
from types import SimpleNamespace

import httpx2
import openai
import pytest

# The tests never send traces, even when .env holds Langfuse keys.
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

from eventai.llm import Provider  # noqa: E402
from eventai.rag.search_text import tokenize  # noqa: E402


class FakeEmbedder:
    """Bag-of-words hashed into a vector: fast, offline, and similar words give similar vectors."""

    dimensions = 4096  # wide enough that unrelated words seldom share a slot

    def _vector(self, text):
        vector = [0.0] * self.dimensions
        vector[0] = 0.01  # never a zero vector
        for token in tokenize(text):
            vector[1 + int(hashlib.md5(token.encode()).hexdigest(), 16) % (self.dimensions - 1)] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector]

    def passages(self, texts):
        return [self._vector(t) for t in texts]

    def query(self, text):
        return self._vector(text)


@pytest.fixture(scope="session")
def fake_embedder():
    return FakeEmbedder()


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
        if isinstance(out, SimpleNamespace):  # a raw response, for odd provider replies
            return out
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
