"""Part 2 starts itself (D18): find the upcoming events in Calendar, run the saved Langflow flow for each, and
with --watch, run again when the event's RSVP emails change.

    python -m eventai.agent.run                                # each upcoming event, once
    python -m eventai.agent.run --event-id partnersummit2026   # one event
    python -m eventai.agent.run --watch --every 60             # check Gmail each minute; run on new RSVP emails

The Langflow server runs the flow (langflow_part2/serve.sh), so each run has its Langfuse trace. This command
only reads Calendar and Gmail (the agent's read-only token) and adds the trigger to the run report.
Publishing the outputs to the website stays a deliberate commit and push.
"""

import argparse
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import requests

from eventai.agent.schema import Event
from eventai.agent.tools import ToolError
from eventai.agent.tools.calendar import get_event, upcoming_events
from eventai.agent.tools.gmail import rsvp_message_ids
from eventai.agent.tools.google_auth import agent_credentials, build_service
from eventai.config import ROOT, load_settings

FLOW_NAME = "Event AI Part 2 Attendee list"
RUN_TIMEOUT_SECONDS = 20 * 60  # the planner brief can wait for the free-model rate limits
REPORT = ROOT / "outputs" / "run_report.json"
STATE = ROOT / ".watch_state.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log(text: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {text}", flush=True)


class Langflow:
    """The two calls the command needs from the local Langflow server's REST API."""

    def __init__(self, url: str, api_key: str | None, session=None):
        self.url, self.api_key = url.rstrip("/"), api_key
        self.session = session or requests.Session()

    def _call(self, method: str, path: str, timeout: int, **kwargs) -> dict | list:
        try:
            response = self.session.request(method, f"{self.url}/api/v1/{path}", timeout=timeout,
                                            headers={"x-api-key": self.api_key or ""}, **kwargs)
        except requests.ConnectionError as err:
            raise ToolError(f"Langflow does not answer at {self.url}: start it with langflow_part2/serve.sh") from err
        except requests.Timeout as err:
            raise ToolError(f"Langflow {path} took longer than {timeout} s") from err
        if response.status_code >= 400:
            raise ToolError(f"Langflow {path} failed: HTTP {response.status_code} {response.text[:200]}")
        return response.json()

    def flow_id(self, name: str = FLOW_NAME) -> str:
        flows = self._call("GET", "flows/", 30, params={"get_all": "true", "header_flows": "true",
                                                        "remove_example_flows": "true"})
        flows = flows if isinstance(flows, list) else flows.get("items", [])
        ids = [f["id"] for f in flows if f.get("name") == name]
        if not ids:
            raise ToolError(f"Langflow has no flow named {name!r} (langflow_part2/WIRING.md, step 1)")
        return ids[0]

    def run(self, flow_id: str, event_id: str, session_id: str) -> str:
        """Run the flow with the event ID as the chat input; return the Chat Output summary."""
        result = self._call("POST", f"run/{flow_id}", RUN_TIMEOUT_SECONDS,
                            json={"input_value": event_id, "input_type": "chat", "output_type": "chat",
                                  "session_id": session_id})
        return "\n".join(o["results"]["message"]["text"] for out in result.get("outputs", [])
                         for o in out.get("outputs", []) if (o.get("results") or {}).get("message"))


def record_trigger(trigger: dict, started_at: datetime, report: Path = REPORT) -> bool:
    """Add the trigger to the run report, but only to a report that this run wrote."""
    if not report.exists() or report.stat().st_mtime < started_at.timestamp():
        return False
    data = json.loads(report.read_text())
    report.write_text(json.dumps({**data, "trigger": trigger}, indent=2, default=str) + "\n")
    return True


def run_event(langflow: Langflow, flow_id: str, event_id: str, started_by: str, reason: str,
              report: Path = REPORT, clock: Callable[[], datetime] = _now) -> str:
    started = clock()
    session_id = f"{event_id}-{started:%Y%m%dT%H%M%SZ}"  # a new chat session for each run
    summary = langflow.run(flow_id, event_id, session_id)
    record_trigger({"started_by": started_by, "reason": reason, "event_id": event_id, "session_id": session_id,
                    "started_at": started.isoformat(timespec="seconds"),
                    "finished_at": clock().isoformat(timespec="seconds")}, started, report)
    return summary


def change(seen: list[str] | None, ids: list[str]) -> str | None:
    """Why an event needs a run: None when its RSVP emails are the same as at its last good run."""
    if seen is None:
        return "no earlier run"
    new, gone = len(set(ids) - set(seen)), len(set(seen) - set(ids))
    if not new and not gone:
        return None
    parts = [f"{new} new RSVP email{'s' * (new != 1)}"] if new else []
    return ", ".join(parts + ([f"{gone} removed"] if gone else []))


def check(events: list[Event], message_ids: Callable[[Event], list[str]], run: Callable[[str, str], str],
          state: dict, force: str | None = None, clock: Callable[[], datetime] = _now) -> list[str]:
    """One pass: run each event whose RSVP emails changed (or each event, with `force` as the reason).
    The state keeps the email IDs of each event's last good run, so a failed run is tried again next time."""
    ran = []
    for event in events:
        ids = sorted(message_ids(event))
        reason = force or change(state.get(event.event_id, {}).get("emails"), ids)
        if reason is None:
            continue
        log(f"{event.event_id}: {reason} -> running the flow")
        try:
            log(run(event.event_id, reason) or "(no summary)")
        except ToolError as err:
            log(f"{event.event_id}: the run failed, so the next check tries again: {err}")
            continue
        state[event.event_id] = {"emails": ids, "last_run": clock().isoformat(timespec="seconds")}
        ran.append(event.event_id)
    return ran


def load_state(path: Path = STATE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(state: dict, path: Path = STATE) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event-id", help="run this event only (default: each upcoming event in Calendar)")
    parser.add_argument("--days", type=int, default=60, help="how many days ahead to look for events")
    parser.add_argument("--watch", action="store_true", help="keep checking Gmail; run when RSVP emails change")
    parser.add_argument("--every", type=int, default=300, help="seconds between checks, with --watch")
    args = parser.parse_args(argv)

    settings = load_settings()
    langflow = Langflow(settings.langflow_url, settings.langflow_api_key)
    started_by = "watch" if args.watch else "command"
    try:
        flow = langflow.flow_id()
        credentials = agent_credentials()
    except ToolError as err:
        raise SystemExit(str(err)) from err
    calendar, gmail = build_service("calendar", "v3", credentials), build_service("gmail", "v1", credentials)

    def events() -> list[Event]:
        found = [get_event(calendar, args.event_id)] if args.event_id else upcoming_events(calendar, args.days)
        if not found:
            log(f"No event with a venue in the next {args.days} days.")
        return found

    def run(event_id: str, reason: str) -> str:
        return run_event(langflow, flow, event_id, started_by, reason)

    state = load_state()
    if not args.watch:
        try:
            found = events()
            ran = check(found, lambda e: rsvp_message_ids(gmail, e), run, state, force="started by hand")
        except ToolError as err:
            raise SystemExit(str(err)) from err
        save_state(state)
        if len(ran) < len(found):
            raise SystemExit(1)
        return
    log(f"Watching Gmail every {args.every} s for RSVP emails. Stop with Ctrl+C.")
    try:
        while True:
            try:
                check(events(), lambda e: rsvp_message_ids(gmail, e), run, state)
                save_state(state)
            except ToolError as err:  # Google or Langflow is down: try again at the next check
                log(f"The check failed: {err}")
            time.sleep(args.every)
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == "__main__":
    main()
