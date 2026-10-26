from eventai import tracing


def test_tracing_is_off_in_tests_and_the_helpers_still_work(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_initialised", False)

    assert tracing.init_tracing() is None  # conftest sets LANGFUSE_TRACING_ENABLED=false
    with tracing.observation("step", as_type="tool", input={"a": 1}) as obs:
        obs.update(output={"b": 2})
    assert tracing.current_trace_id() is None
    assert tracing.trace_url("abc") is None
    tracing.flush()


def test_tracing_is_off_without_keys(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_initialised", False)
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    settings = tracing.load_settings().model_copy(update={"langfuse_public_key": None, "langfuse_secret_key": None})
    monkeypatch.setattr(tracing, "load_settings", lambda: settings)

    assert tracing.init_tracing() is None
