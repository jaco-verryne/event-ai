"""The Part 2 results page helpers (D6), on a real seed run: canned extractions, the code checks, the code
check of decisions, and write_outputs. No LLM call."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eventai.agent import checks, results
from eventai.agent.output import write_outputs
from eventai.agent.review import Decision, apply_decisions
from eventai.agent.schema import ExtractedRsvp
from eventai.agent.tools.seed_files import load_crm, load_emails, load_event

NOT_FOUND = SimpleNamespace(found=False, number=None, name=None, status=None)
BRIEF = {"event_id": "partnersummit2026", "event_summary": "Northern Partners Summit 2026", "event_date": "2026-11-26",
         "answers": [{"topic": "data retention", "question": "How long?", "answer": "30 days after the event.",
                      "facts": [], "source_ids": ["policies.csv#POL-DAT-02"], "confidence": "high"}],
         "deadlines": [], "todo": ["Delete the guests' dietary and access information by Sat 26 Dec 2026"]}
TRIGGER = {"started_by": "watch", "reason": "1 new RSVP email", "event_id": "partnersummit2026",
           "started_at": "2026-10-28T02:14:05+00:00", "finished_at": "2026-10-28T02:17:35+00:00"}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    canned = yaml.safe_load((Path(__file__).parent / "fixtures" / "part2_extractions.yaml").read_text())
    emails, event, crm = load_emails(), load_event(), load_crm()
    attendees, audit, report = checks.check_all([(e, ExtractedRsvp(**canned[e.key])) for e in emails], event=event,
                                                crm=crm, companies=lambda n: NOT_FOUND, seated_capacity=100)
    ids = {";".join(a.source_keys): a.attendee_id for a in attendees}
    decisions = [  # one accepted fix, one value that is not in the evidence; the other flags get no decision
        Decision(attendee_id=ids["e10"], flag="phone_invalid", action="use_value", value="+441134960712",
                 source="crm.csv#C007", reason="The CRM row has the phone."),
        Decision(attendee_id=ids["e07"], flag="name_differs_from_crm", action="use_value", value="Bobby Harper",
                 source="crm.csv#C006", reason="A guess."),
    ]
    attendees, resolved = apply_decisions(attendees, decisions, emails=emails, crm=crm, event=event)
    folder = tmp_path_factory.mktemp("outputs")
    report = {**report, "resolutions": {"use_value": 1, "human_review": 4}, "trigger": TRIGGER}
    write_outputs(folder, attendees, audit + resolved, report, brief=BRIEF)
    return SimpleNamespace(outputs=results.load_outputs(folder), ids=ids, folder=folder)


def row(run, key):
    return next(r for r in run.outputs.rows if r["attendee_id"] == run.ids[key])


def test_load_outputs_reads_the_four_files(run):
    out = run.outputs
    assert len(out.rows) == 11 and out.audit and out.report["emails"] == 13
    assert out.brief_md.startswith("# Planner brief")


def test_no_run_and_missing_files(tmp_path):
    assert results.load_outputs(tmp_path) is None
    (tmp_path / "attendees.csv").write_text("attendee_id,source_keys\nA01,e01\n")
    partial = results.load_outputs(tmp_path)
    assert partial.audit == [] and partial.report == {} and partial.brief_md is None


@pytest.mark.parametrize("source, expected", [
    ("gmail:18f2a", "Google Calendar and Gmail (demo account, read-only)"),
    ("seed:e01 + crm.csv#C001", "the seed files (offline)"),
    ("crm.csv#C001", "an unknown source"),
])
def test_run_source(source, expected):
    assert results.run_source([{"email_source": source, "email": "x"}]) == expected


def test_event_and_trigger_lines(run):
    assert results.event_line(run.outputs.report) == (
        "Northern Partners Summit 2026 · Thu 26 Nov 2026 · 9 attending, 100 seats at the venue")
    assert results.trigger_line(run.outputs.report) == (
        "Started by the Gmail watcher on Wed 28 Oct 2026 at 02:14 UTC (1 new RSVP email). The run took 3 min 30 s.")
    assert results.trigger_line({}) is None  # a Playground run


def test_summary_metrics(run):
    metrics = {label: value for label, value, _ in results.summary_metrics(run.outputs.report)}
    assert metrics == {"RSVP emails": "13", "Attendees": "11", "Attending": "9 of 100", "Flagged for review": "5",
                       "Agent fixes accepted": "1", "Human review": "4"}


def test_decision_rows_pair_each_flag_with_its_code_check(run):
    rows = {(r["Attendee"], r["Flag"]): r for r in results.decision_rows(run.outputs.rows, run.outputs.audit)}
    assert len(rows) == 5
    fixed = rows[(run.ids["e10"], "phone_invalid")]
    assert (fixed["Decision"], fixed["New value"], fixed["Source"]) == (
        "use the value from the evidence", "+441134960712", "crm.csv#C007")
    guessed = rows[(run.ids["e07"], "name_differs_from_crm")]
    assert guessed["Decision"] == "human review" and "value not in evidence" in guessed["Reason"]
    silent = rows[(run.ids["e12"], "attendance_unclear")]
    assert silent["Decision"] == "human review" and silent["Reason"] == "no decision from the agent"


def test_audit_rows_follow_the_record_back_to_its_emails(run):
    merged = row(run, "e05;e06")
    steps = results.audit_rows(run.outputs.audit, merged)
    assert {"normalize", "dedupe"} <= {s["Step"] for s in steps}
    assert all(s["Step"] != "resolve" for s in steps)  # A04 had no flag
    assert any(s["Step"] == "resolve" for s in results.audit_rows(run.outputs.audit, row(run, "e10")))


def test_field_rows_give_a_status_and_a_source_for_each_field(run):
    fields = {f["Field"]: f for f in results.field_rows(row(run, "e10"))}
    assert fields["phone"]["Status"] == "corrected" and fields["phone"]["Source"] == "crm.csv#C007"
    assert fields["company_number"]["Status"] == "absent"


def test_attendee_table_colours_each_value_by_its_status(run):
    styler = results.attendee_table(run.outputs.rows)
    html = styler.to_html()
    assert results.STATUS_COLOURS["corrected"] in html and results.STATUS_COLOURS["conflict"] in html
    assert list(styler.data.columns)[:2] == ["ID", "Name"] and len(styler.data) == 11


def test_latest_score_skips_the_part1_files(tmp_path):
    assert results.latest_score(tmp_path) is None
    for name in ("2026-10-26_part1.json", "2026-10-27_part2.json", "2026-10-28_part2.json"):
        (tmp_path / name).write_text(json.dumps({"name": name}))
    assert results.latest_score(tmp_path) == ("2026-10-28", {"name": "2026-10-28_part2.json"})


def test_score_metrics():
    score = {"flags": {"precision": 1.0, "recall": 1.0}, "fields": {"correct": 75, "total": 77},
             "deduplication": {"exact_groups": 11, "expected_groups": 11}, "resolutions": {"correct": 4, "total": 5},
             "brief": {"ran": True, "expected_sources_cited": ["a", "b", "c"], "expected_sources_missed": ["d"]}}
    assert dict(results.score_metrics(score)) == {
        "Flag precision": "100%", "Flag recall": "100%", "Field values right": "75 of 77", "Merges exact": "11 of 11",
        "Decisions as expected": "4 of 5", "Brief sources cited": "3 of 4"}


def test_brief_view_has_three_shapes(run):
    assert results.brief_view(run.outputs.report)[0] == "ok"
    assert results.brief_view({"brief": {"error": "DailyLimitReached"}}) == ("error", "DailyLimitReached")
    assert results.brief_view({}) == ("missing", None)
    assert results.brief_view({"brief": {"dry_run": True, "questions": []}}) == ("missing", None)
