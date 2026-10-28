"""The Part 2 results page (D6): read the last run's committed files and shape them for the page.
pages/part2_results.py stays thin; these helpers are plain and tested. No LLM call, no keys."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from eventai.agent.output import read_rows
from eventai.agent.schema import FIELDS
from eventai.config import ROOT

OUTPUTS = ROOT / "outputs"
RESULTS = ROOT / "eval" / "results"
# The colours of the diagrams: green verified, blue corrected, grey absent, red conflict.
STATUS_COLOURS = {"verified": "#d5e8d4", "corrected": "#dae8fc", "absent": "#f5f5f5", "conflict": "#f8cecc"}
TABLE_FIELDS = {"full_name": "Name", "email": "Email", "phone": "Phone", "company": "Company",
                "job_title": "Job title", "dietary_needs": "Dietary needs", "attending": "Attending"}
ACTIONS = {"use_value": "use the value from the evidence", "keep": "keep the value", "human_review": "human review"}
STARTED_BY = {"watch": "the Gmail watcher", "command": "the run command"}


@dataclass
class RunOutputs:
    rows: list[dict[str, str]]
    audit: list[dict]
    report: dict
    brief_md: str | None
    folder: Path


def _split(cell: str | None) -> list[str]:
    return [part for part in (cell or "").split(";") if part]


def load_outputs(folder: Path = OUTPUTS) -> RunOutputs | None:
    """The last run, or None when no run is committed. A missing file gives an empty value."""
    if not (folder / "attendees.csv").exists():
        return None

    def read_json(name: str, empty):
        path = folder / name
        return json.loads(path.read_text()) if path.exists() else empty

    brief = folder / "planner_brief.md"
    return RunOutputs(read_rows(folder / "attendees.csv"), read_json("audit_log.json", []),
                      read_json("run_report.json", {}), brief.read_text() if brief.exists() else None, folder)


def run_source(rows: list[dict]) -> str:
    sources = " ".join(v for r in rows for k, v in r.items() if k.endswith("_source") and v)
    if "gmail:" in sources:
        return "Google Calendar and Gmail (demo account, read-only)"
    return "the seed files (offline)" if "seed:" in sources else "an unknown source"


def event_line(report: dict) -> str:
    brief = report.get("brief") or {}
    parts = [brief.get("event_summary") or brief.get("event_id") or (report.get("trigger") or {}).get("event_id")
             or "The event"]
    if brief.get("event_date"):
        parts.append(f"{date.fromisoformat(brief['event_date']):%a %d %b %Y}")
    capacity = report.get("capacity") or {}
    if capacity.get("seated_capacity"):
        parts.append(f"{capacity.get('attending', 0)} attending, {capacity['seated_capacity']} seats at the venue")
    return " · ".join(parts)


def trigger_line(report: dict) -> str | None:
    """Who started the run and why (D18). A run from the Langflow Playground has no trigger."""
    trigger = report.get("trigger")
    if not trigger:
        return None
    started = datetime.fromisoformat(trigger["started_at"])
    minutes, seconds = divmod(int((datetime.fromisoformat(trigger["finished_at"]) - started).total_seconds()), 60)
    who = STARTED_BY.get(trigger.get("started_by"), trigger.get("started_by"))
    return (f"Started by {who} on {started:%a %d %b %Y at %H:%M} UTC ({trigger.get('reason')}). "
            f"The run took {minutes} min {seconds} s.")


def summary_metrics(report: dict) -> list[tuple[str, str, str]]:
    """(label, value, help) for the row of numbers at the top of the page."""
    capacity, resolutions = report.get("capacity") or {}, report.get("resolutions") or {}
    review = report.get("for_review") or []
    seats = capacity.get("seated_capacity")
    return [
        ("RSVP emails", str(report.get("emails", 0)), "The replies that the Gmail search found for the event."),
        ("Attendees", str(report.get("attendees", 0)),
         f"{report.get('merged_emails', 0)} emails were merged as duplicates of another reply."),
        ("Attending", f"{capacity.get('attending', 0)} of {seats}" if seats else str(capacity.get("attending", 0)),
         "Over the venue capacity." if capacity.get("over_capacity") else "Within the venue's seated capacity."),
        ("Flagged for review", str(len(review)), ", ".join(review) or "No record needed the agent."),
        ("Agent fixes accepted", str(resolutions.get("use_value", 0)),
         "Values that the agent proposed and that code found in the evidence."),
        ("Human review", str(resolutions.get("human_review", 0)),
         "Flags that the evidence does not settle, or that a person must decide."),
    ]


def latest_score(folder: Path = RESULTS) -> tuple[str, dict] | None:
    """The newest Part 2 score (eval/run_part2.py), as (date, scores)."""
    files = sorted(folder.glob("*_part2.json"))
    return (files[-1].name.split("_")[0], json.loads(files[-1].read_text())) if files else None


def score_metrics(score: dict) -> list[tuple[str, str]]:
    flags, fields, merges, decisions = score["flags"], score["fields"], score["deduplication"], score["resolutions"]
    metrics = [("Flag precision", f"{flags['precision']:.0%}"), ("Flag recall", f"{flags['recall']:.0%}"),
               ("Field values right", f"{fields['correct']} of {fields['total']}"),
               ("Merges exact", f"{merges['exact_groups']} of {merges['expected_groups']}"),
               ("Decisions as expected", f"{decisions['correct']} of {decisions['total']}")]
    brief = score.get("brief") or {}
    if brief.get("ran"):
        cited, missed = brief["expected_sources_cited"], brief["expected_sources_missed"]
        metrics.append(("Brief sources cited", f"{len(cited)} of {len(cited) + len(missed)}"))
    return metrics


def _style(status: str | None) -> str:
    return f"background-color: {STATUS_COLOURS[status]}; color: #000000" if status in STATUS_COLOURS else ""


def attendee_table(rows: list[dict]):
    """The attendee list, each value coloured by its status (a pandas Styler for st.dataframe)."""
    columns = {"attendee_id": "ID", **TABLE_FIELDS, "flags": "Flags", "resolution": "Decisions"}
    frame = pd.DataFrame([{label: ", ".join(_split(r.get(key))) if key in ("flags", "resolution") else r.get(key, "")
                           for key, label in columns.items()} for r in rows], columns=list(columns.values()))
    styles = pd.DataFrame([{label: _style(r.get(f"{key}_status")) if key in TABLE_FIELDS else ""
                            for key, label in columns.items()} for r in rows], columns=list(columns.values()))
    return frame.style.apply(lambda _: styles, axis=None)


def decision_rows(rows: list[dict], audit: list[dict]) -> list[dict]:
    """One row for each flag the agent step decided. Apply Decisions writes one 'resolve' entry for each
    flag, in the order of the record's resolutions, so the two lists pair up in order."""
    entries = defaultdict(list)
    for entry in audit:
        if entry.get("step") == "resolve":
            entries[entry.get("attendee_id")].append(entry)
    out = []
    for row in rows:
        pending = iter(entries[row["attendee_id"]])
        for item in _split(row.get("resolution")):
            flag, _, action = item.rpartition(":")
            entry = next(pending, {})
            out.append({"Attendee": row["attendee_id"], "Name": row.get("full_name", ""), "Flag": flag,
                        "Decision": ACTIONS.get(action, action), "New value": entry.get("after") or "",
                        "Source": entry.get("source") or "", "Reason": entry.get("note") or ""})
    return out


def field_rows(row: dict) -> list[dict]:
    return [{"Field": field, "Value": row.get(field, ""), "Status": row.get(f"{field}_status", ""),
             "Source": row.get(f"{field}_source", ""), "Note": row.get(f"{field}_note", "")} for field in FIELDS]


def audit_rows(audit: list[dict], row: dict) -> list[dict]:
    """The audit trail of one record: its own entries, and the entries of its emails before the merge."""
    keys = set(_split(row.get("source_keys")))
    return [{"Step": e.get("step", ""), "Action": e.get("action", ""), "Field": e.get("field") or "",
             "Before": e.get("before") or "", "After": e.get("after") or "", "Source": e.get("source") or "",
             "Note": e.get("note") or ""}
            for e in audit
            if e.get("attendee_id") == row["attendee_id"] or (not e.get("attendee_id") and e.get("email_key") in keys)]


def brief_view(report: dict) -> tuple[str, dict | str | None]:
    """('ok', brief) with Part 1's answers, ('error', message) when the brief failed, or ('missing', None)."""
    brief = report.get("brief")
    if not brief:
        return "missing", None
    if "error" in brief:
        return "error", brief["error"]
    return ("ok", brief) if "answers" in brief else ("missing", None)
