"""Langfuse traces (D10). With no keys, or LANGFUSE_TRACING_ENABLED=false, tracing is off and the
app works the same."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse, propagate_attributes

from eventai.config import get, load_settings

_client: Langfuse | None = None
_initialised = False


def init_tracing(environment: str = "app") -> Langfuse | None:
    """Make the one Langfuse client. The first call wins, so a process has one environment."""
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True
    settings = load_settings()
    enabled = (get("LANGFUSE_TRACING_ENABLED") or "true").lower() != "false"
    if not (enabled and settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    # Keys come from config (Streamlit secrets or .env), not only from the environment.
    _client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host,
        environment=environment,
    )
    # Importing the wrapper instruments every OpenAI client: each LLM call becomes a generation.
    import langfuse.openai  # noqa: F401

    return _client


class _NoObservation:
    def update(self, **kwargs: Any) -> None:
        pass


@contextmanager
def observation(name: str, as_type: str = "span", input: Any = None) -> Iterator[Any]:
    """A Langfuse observation, or a no-op when tracing is off."""
    client = init_tracing()
    if client is None:
        yield _NoObservation()
        return
    with client.start_as_current_observation(name=name, as_type=as_type, input=input) as obs:
        yield obs


@contextmanager
def session(session_id: str | None) -> Iterator[None]:
    """Group the traces of one chat as one Langfuse session. A no-op when tracing is off."""
    if init_tracing() is None or not session_id:
        yield
        return
    with propagate_attributes(session_id=session_id):
        yield


def current_trace_id() -> str | None:
    client = init_tracing()
    return client.get_current_trace_id() if client else None


def trace_url(trace_id: str | None) -> str | None:
    client = init_tracing()
    return client.get_trace_url(trace_id=trace_id) if client and trace_id else None


def flush() -> None:
    """Send the open traces now. Scripts call this before they exit."""
    if _client is not None:
        _client.flush()
