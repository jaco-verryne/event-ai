"""The planner brief (D17): the questions to Part 1, the deadlines from the cited rules, and the CLI."""

import json
import subprocess
import sys
from datetime import date
from types import SimpleNamespace

import pytest
import yaml

from eventai.agent import checks
from eventai.agent.brief import brief_markdown, brief_questions, deadline, policy_table, run_brief, todo_lines
from eventai.agent.schema import ExtractedRsvp
from eventai.agent.tools.seed_files import SEED_DIR, load_crm, load_emails, load_event
from eventai.config import ROOT
from eventai.rag.answer import Answer, Fact

NOT_FOUND = SimpleNamespace(found=False, number=None, name=None, status=None)
EVENT_DAY = date(2026, 11, 26)  # a Thursday


@pytest.fixture(scope="module")
def run():
    canned = yaml.safe_load((SEED_DIR.parent / "tests" / "fixtures" / "part2_extractions.yaml").read_text())
    event = load_event()
    attendees, _, _ = checks.check_all([(e, ExtractedRsvp(**canned[e.key])) for e in load_emails()], event=event,
                                       crm=load_crm(), companies=lambda n: NOT_FOUND, seated_capacity=100)
    return event, attendees


def test_questions_use_the_run_data(run):
    event, attendees = run
    questions = {q["topic"]: q["question"] for q in brief_questions(event, attendees)}
    assert list(questions) == ["guest numbers", "dietary needs", "venue and access", "data retention"]
    assert "26 November 2026" in questions["guest numbers"]
    assert questions["dietary needs"].endswith("these needs: no nuts; vegetarian?")
    assert "Roundhay Hall (V113)" in questions["venue and access"]


def test_no_dietary_question_without_dietary_needs(run):
    event, attendees = run
    plain = [a.model_copy(update={"dietary_needs": checks.absent()}) for a in attendees]
    assert "dietary needs" not in [q["topic"] for q in brief_questions(event, plain)]


@pytest.mark.parametrize("rule, expected", [
    ("Final guest numbers are due 10 working days before the event.", date(2026, 11, 12)),
    ("Send the dietary needs and allergies of each guest 14 days before the event.", date(2026, 11, 12)),
    ("We delete this health information 30 days after the event.", date(2026, 12, 26)),
    ("Final guest numbers are due 21 days before the event.", date(2026, 11, 5)),
    ("The caterer tries to meet them.", None),
])
def test_deadline(rule, expected):
    assert deadline(rule, EVENT_DAY) == expected


def fake_ask(answers):
    def ask(question, history, resources, providers, session_id):
        source_ids = answers[next(k for k in answers if k in question)]
        facts = [Fact(label="rule", value="x", source_id=s) for s in source_ids]
        return SimpleNamespace(answer=Answer(answer=f"answer to: {question[:20]}", facts=facts, source_ids=source_ids,
                                             confidence="high"), trace_id="trace-1")
    return ask


def test_run_brief_turns_the_cited_rules_into_deadlines(run):
    event, attendees = run
    ask = fake_ask({"guest numbers": ["policies.csv#POL-GST-01", "policies.csv#POL-GST-02"],
                    "dietary needs": ["policies.csv#POL-DIE-01", "policies.csv#POL-DIE-03"],
                    "Roundhay Hall": ["venues.csv#V113", "policies.csv#POL-ACC-02"],
                    "how long": ["policies.csv#POL-DAT-02"], "How long": ["policies.csv#POL-DAT-02"]})
    brief = run_brief(event, attendees, ask_fn=ask, resources=None, policies=policy_table())
    assert len(brief["answers"]) == 4 and brief["answers"][0]["trace_id"] == "trace-1"
    # POL-GST-02 is for the Gala Dinner only, so it sets no deadline for this event.
    assert [(d["policy_id"], d["date"]) for d in brief["deadlines"]] == [
        ("POL-GST-01", "2026-11-12"), ("POL-DIE-01", "2026-11-12"), ("POL-DAT-02", "2026-12-26")]
    assert brief["todo"] == [
        "Send the final guest numbers (9 attending) by Thu 12 Nov 2026 (policies.csv#POL-GST-01)",
        "Send the dietary needs and allergies (no nuts; vegetarian) by Thu 12 Nov 2026 (policies.csv#POL-DIE-01)",
        "Delete the guests' dietary and access information by Sat 26 Dec 2026 (policies.csv#POL-DAT-02)"]
    text = brief_markdown(brief)
    assert text.startswith("# Planner brief: Northern Partners Summit 2026")
    assert "## To do" in text and "## Venue and access" in text and "Sources: venues.csv#V113" in text
    assert "The brief failed: timeout" in brief_markdown({"event_id": "x", "error": "timeout"})
    dry = brief_markdown({"dry_run": True, "questions": [{"topic": "guest numbers", "question": "When?"}]})
    assert "Dry run" in dry and "- guest numbers: When?" in dry
    assert todo_lines({"deadlines": []}, attendees) == []


def test_cli_dry_run_asks_nothing(run):
    event, attendees = run
    payload = json.dumps({"event": event.model_dump(mode="json"), "attendees": [a.model_dump(mode="json") for a in attendees]})
    out = subprocess.run([sys.executable, "-m", "eventai.agent.brief", "--dry-run"], input=payload, cwd=ROOT,
                         capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert result["dry_run"] and len(result["questions"]) == 4


def test_the_brief_waits_on_a_rate_limit_and_goes_on_after_a_failure(run):
    from eventai.llm import DailyLimitReached

    event, attendees = run
    calls, waits = [], []
    good = fake_ask({"": ["policies.csv#POL-DAT-02"]})

    def ask(question, *args):
        calls.append(question)
        if "guest numbers" in question and len(calls) == 1:
            raise DailyLimitReached("all providers are rate-limited")  # once: the retry works
        if "Roundhay Hall" in question:
            raise RuntimeError("provider down")
        return good(question, *args)

    brief = run_brief(event, attendees, ask_fn=ask, resources=None, policies=policy_table(), sleep=waits.append)
    assert waits == [65]
    assert [("error" in a) for a in brief["answers"]] == [False, False, True, False]
    assert "No answer: RuntimeError: provider down" in brief_markdown(brief)
