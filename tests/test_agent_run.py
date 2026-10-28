"""The run command and the watcher (D18), offline: a fake Langflow server and fake Gmail IDs."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

from eventai.agent import run as runner
from eventai.agent.tools import ToolError
from eventai.agent.tools.seed_files import load_event

T0 = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code, data=None, text=""):
        self.status_code, self._data, self.text = status_code, data, text

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, timeout, headers, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, "headers": headers, **kwargs})
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def langflow(*outcomes):
    session = FakeSession(*outcomes)
    return runner.Langflow("http://127.0.0.1:7860/", "lf-key", session=session), session


def run_response(text):
    return FakeResponse(200, {"session_id": "s", "outputs": [{"inputs": {}, "outputs": [
        {"results": {"message": {"text": text}}}]}]})


# Langflow API

def test_flow_id_finds_the_saved_flow_by_name():
    lf, session = langflow(FakeResponse(200, [{"id": "f0", "name": "Spike"}, {"id": "f1", "name": runner.FLOW_NAME}]))
    assert lf.flow_id() == "f1"
    call = session.calls[0]
    assert call["url"] == "http://127.0.0.1:7860/api/v1/flows/"
    assert call["headers"] == {"x-api-key": "lf-key"}
    assert call["params"]["header_flows"] == "true"


def test_a_missing_flow_is_a_clear_error():
    lf, _ = langflow(FakeResponse(200, {"items": []}))
    with pytest.raises(ToolError, match="no flow named"):
        lf.flow_id()


def test_run_sends_the_event_id_and_returns_the_summary():
    lf, session = langflow(run_response("13 emails -> 11 attendees (2 merged)."))
    assert lf.run("f1", "partnersummit2026", "partnersummit2026-20261028T020000Z").startswith("13 emails")
    call = session.calls[0]
    assert call["method"] == "POST" and call["url"].endswith("/api/v1/run/f1")
    assert call["json"]["input_value"] == "partnersummit2026"
    assert call["json"]["session_id"] == "partnersummit2026-20261028T020000Z"
    assert call["timeout"] == runner.RUN_TIMEOUT_SECONDS


def test_no_server_says_how_to_start_it():
    lf, _ = langflow(requests.ConnectionError("refused"))
    with pytest.raises(ToolError, match="serve.sh"):
        lf.flow_id()


def test_an_http_error_is_a_tool_error():
    lf, _ = langflow(FakeResponse(500, text="Internal error"))
    with pytest.raises(ToolError, match="HTTP 500"):
        lf.run("f1", "partnersummit2026", "s")


# The trigger in the run report

def test_the_trigger_goes_only_into_a_report_that_this_run_wrote(tmp_path):
    report = tmp_path / "run_report.json"
    report.write_text(json.dumps({"emails": 13}))
    old = T0.timestamp() - 3600
    os.utime(report, (old, old))
    assert not runner.record_trigger({"started_by": "watch"}, T0, report)
    assert "trigger" not in json.loads(report.read_text())
    os.utime(report, (T0.timestamp() + 60, T0.timestamp() + 60))
    assert runner.record_trigger({"started_by": "watch"}, T0, report)
    assert json.loads(report.read_text()) == {"emails": 13, "trigger": {"started_by": "watch"}}


def test_run_event_records_who_started_the_run_and_why(tmp_path):
    report = tmp_path / "run_report.json"

    class FlowWritesTheReport:
        def run(self, flow_id, event_id, session_id):
            report.write_text(json.dumps({"emails": 14}))
            return "14 emails -> 12 attendees."

    ticks = iter([datetime.now(timezone.utc) - timedelta(seconds=5), datetime.now(timezone.utc)])
    summary = runner.run_event(FlowWritesTheReport(), "f1", "partnersummit2026", "watch", "1 new RSVP email",
                               report=report, clock=lambda: next(ticks))
    trigger = json.loads(report.read_text())["trigger"]
    assert summary.startswith("14 emails")
    assert trigger["started_by"] == "watch" and trigger["reason"] == "1 new RSVP email"
    assert trigger["session_id"].startswith("partnersummit2026-") and trigger["finished_at"] >= trigger["started_at"]


# The watcher

@pytest.mark.parametrize("seen, ids, expected", [
    (None, ["a"], "no earlier run"),
    (["a", "b"], ["a", "b"], None),
    (["a", "b"], ["a", "b", "c"], "1 new RSVP email"),
    (["a", "b"], ["c", "d", "a"], "2 new RSVP emails, 1 removed"),
])
def test_change(seen, ids, expected):
    assert runner.change(seen, ids) == expected


def events(*ids):
    seed = load_event()
    return [seed.model_copy(update={"event_id": i}) for i in ids]


def test_check_runs_only_the_events_whose_emails_changed():
    state = {"quiet": {"emails": ["q1"]}, "busy": {"emails": ["b1"]}}
    inbox = {"quiet": ["q1"], "busy": ["b1", "b2"]}
    ran = []
    result = runner.check(events("quiet", "busy"), lambda e: inbox[e.event_id],
                          lambda event_id, reason: ran.append((event_id, reason)) or "ok", state, clock=lambda: T0)
    assert result == ["busy"] and ran == [("busy", "1 new RSVP email")]
    assert state["busy"] == {"emails": ["b1", "b2"], "last_run": "2026-10-28T02:00:00+00:00"}
    assert state["quiet"] == {"emails": ["q1"]}


def test_a_failed_run_keeps_the_old_state_so_the_next_check_tries_again():
    state = {"busy": {"emails": ["b1"]}}

    def fails(event_id, reason):
        raise ToolError("Langflow run failed: HTTP 500")

    assert runner.check(events("busy"), lambda e: ["b1", "b2"], fails, state) == []
    assert state == {"busy": {"emails": ["b1"]}}


def test_the_command_runs_each_event_even_with_no_change():
    state = {"quiet": {"emails": ["q1"]}}
    reasons = []
    runner.check(events("quiet"), lambda e: ["q1"], lambda event_id, reason: reasons.append(reason) or "ok",
                 state, force="started by hand")
    assert reasons == ["started by hand"]


def test_the_state_file_round_trip(tmp_path):
    path = tmp_path / ".watch_state.json"
    assert runner.load_state(path) == {}
    runner.save_state({"partnersummit2026": {"emails": ["a"]}}, path)
    assert runner.load_state(path) == {"partnersummit2026": {"emails": ["a"]}}
