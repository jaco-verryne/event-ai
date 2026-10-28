"""The planner brief (D17): after the attendee list is final, Part 2 asks Part 1, the RAG pipeline, what
the company's policies require for this event. Part 1's answers keep their citations; code turns the
cited rules into dates, because an LLM is not reliable with working-day arithmetic.

    python -m eventai.agent.brief [--dry-run] < {"event": ..., "attendees": [...]}

The Langflow component runs this module in Part 1's own venv (Langflow pins older packages).
"""

import argparse
import contextlib
import csv
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from eventai.agent.schema import Attendee, Event
from eventai.agent.tools.seed_files import venue_row
from eventai.config import ROOT

POLICIES_CSV = ROOT / "data" / "policies.csv"
# Groq's free plan allows 8,000 tokens a minute, and OpenRouter's free models 50 requests a day.
# When every provider gives a rate limit, wait for Groq's next minute (as the Part 1 scorer does).
RATE_LIMIT_WAIT_SECONDS = 65
RATE_LIMIT_ATTEMPTS = 3
_DEADLINE = re.compile(r"(\d+)\s+(working\s+)?days?\s+(before|after)\s+the\s+event", re.IGNORECASE)


def _long_date(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


def brief_questions(event: Event, attendees: list[Attendee]) -> list[dict[str, str]]:
    """The questions for Part 1, built from this run's data. A topic with no data has no question."""
    attending = [a for a in attendees if a.attending.value == "yes"]
    needs = sorted({a.dietary_needs.value for a in attending if a.dietary_needs.value})
    questions = [{"topic": "guest numbers", "question":
                  f"When are final guest numbers due for an event on {_long_date(event.start.date())}, "
                  "and what happens if guest numbers rise after that?"}]
    if needs:
        questions.append({"topic": "dietary needs", "question":
                          "When must we send our guests' dietary needs, and what applies to a guest with these "
                          f"needs: {'; '.join(needs)}?"})
    venue = venue_row(event.venue_id)
    if venue:
        questions.append({"topic": "venue and access", "question":
                          f"Does {venue['name']} ({venue['venue_id']}) have step-free access and in-house catering, "
                          "how many seats does it have, and what can we arrange for guests with access needs?"})
    # Name the policy area: on 28 Oct "dietary and access information" alone sent the router to the dietary
    # and access rules, which do not say how long the data is kept.
    questions.append({"topic": "data retention", "question":
                      "Under our data retention rules, how long may we keep our guests' dietary and access "
                      "information after the event?"})
    return questions


def deadline(rule: str, event_day: date) -> date | None:
    """The date in a rule such as '10 working days before the event'. Weekends only: no bank holidays."""
    match = _DEADLINE.search(rule or "")
    if not match:
        return None
    count, working, direction = int(match.group(1)), bool(match.group(2)), match.group(3).lower()
    step = timedelta(days=-1 if direction == "before" else 1)
    if not working:
        return event_day + step * count
    day = event_day
    while count:
        day += step
        if day.weekday() < 5:
            count -= 1
    return day


def policy_table(path: Path = POLICIES_CSV) -> dict[str, dict[str, str]]:
    with path.open(newline="") as f:
        return {row["policy_id"]: row for row in csv.DictReader(f)}


def todo_lines(brief: dict, attendees: list[Attendee]) -> list[str]:
    """The deadlines as actions, for the run summary and the top of the brief."""
    attending = sum(1 for a in attendees if a.attending.value == "yes")
    needs = sorted({a.dietary_needs.value for a in attendees if a.attending.value == "yes" and a.dietary_needs.value})
    actions = {
        "guest numbers": f"Send the final guest numbers ({attending} attending)",
        "dietary needs": "Send the dietary needs and allergies" + (f" ({'; '.join(needs)})" if needs else ""),
        "data retention": "Delete the guests' dietary and access information",
    }
    lines = []
    for d in brief.get("deadlines", []):
        day = date.fromisoformat(d["date"])
        lines.append(f"{actions.get(d['area'], d['condition'])} by {day:%a %d %b %Y} ({d['source']})")
    return lines


def brief_markdown(brief: dict) -> str:
    """The brief for a planner: the dated actions, then each cited answer."""
    title = f"# Planner brief: {brief.get('event_summary', brief.get('event_id', 'event'))}"
    if "error" in brief:
        return f"{title}\n\nThe brief failed: {brief['error']}\n"
    if brief.get("dry_run"):
        questions = "\n".join(f"- {q['topic']}: {q['question']}" for q in brief["questions"])
        return f"{title}\n\nDry run: the questions only, with no LLM call.\n\n{questions}\n"
    lines = [title, "", f"Event date: {brief['event_date']}. Each answer comes from Part 1, the knowledge-base "
             "assistant, and cites its source. Code computed the dates from the cited rules.", "", "## To do", ""]
    lines += [f"- {t}" for t in brief["todo"]] or ["- No dated actions."]
    for a in brief["answers"]:
        lines += ["", f"## {a['topic'].capitalize()}", "", f"**Question:** {a['question']}", ""]
        if "error" in a:
            lines.append(f"No answer: {a['error']}")
            continue
        lines += [f"**Answer** ({a['confidence']} confidence): {a['answer']}", "",
                  f"Sources: {', '.join(a['source_ids']) or 'none'}"]
    return "\n".join(lines) + "\n"


AskFn = Callable[..., object]  # eventai.rag.pipeline.ask, or a fake in the tests


def _ask_with_wait(ask_fn: AskFn, question: str, resources, providers, session_id, sleep) -> object:
    from eventai.llm import DailyLimitReached

    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        try:
            return ask_fn(question, [], resources, providers, session_id)
        except DailyLimitReached:
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise
            sleep(RATE_LIMIT_WAIT_SECONDS)


def run_brief(event: Event, attendees: list[Attendee], *, ask_fn: AskFn, resources, providers=None,
              session_id: str | None = None, policies: dict[str, dict[str, str]] | None = None,
              sleep: Callable[[float], None] = time.sleep) -> dict:
    policies = policies if policies is not None else policy_table()
    answers, cited = [], []
    for q in brief_questions(event, attendees):
        try:
            result = _ask_with_wait(ask_fn, q["question"], resources, providers, session_id, sleep)
        except Exception as err:  # noqa: BLE001 - one failed question does not stop the brief
            answers.append({**q, "error": f"{type(err).__name__}: {err}"[:300], "source_ids": [], "facts": []})
            continue
        answer = result.answer
        answers.append({**q, "answer": answer.answer, "facts": [f.model_dump() for f in answer.facts],
                        "source_ids": answer.source_ids, "confidence": answer.confidence,
                        "trace_id": getattr(result, "trace_id", None)})
        cited += answer.source_ids + [f.source_id for f in answer.facts]
    deadlines = []
    for source in dict.fromkeys(cited):  # each source once, in the order cited
        policy = policies.get(source.split("#", 1)[1]) if source.startswith("policies.csv#") else None
        # A rule for one package (for example the Gala Dinner) does not set a deadline for this event.
        day = deadline(policy["rule"], event.start.date()) if policy and policy["applies_to"] == "all" else None
        if day:
            deadlines.append({"source": source, "policy_id": policy["policy_id"], "area": policy["area"],
                              "condition": policy["condition"], "rule": policy["rule"], "date": day.isoformat()})
    brief = {"event_id": event.event_id, "event_summary": event.summary, "event_date": event.start.date().isoformat(),
             "answers": answers,
             "deadlines": sorted(deadlines, key=lambda d: d["date"])}
    brief["todo"] = todo_lines(brief, attendees)
    return brief


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The planner brief: Part 2 asks Part 1 (D17).")
    parser.add_argument("--dry-run", action="store_true", help="return the questions only, with no LLM call")
    args = parser.parse_args(argv)
    payload = json.load(sys.stdin)
    event = Event.model_validate(payload["event"])
    attendees = [Attendee.model_validate(a) for a in payload["attendees"]]
    if args.dry_run:
        print(json.dumps({"dry_run": True, "questions": brief_questions(event, attendees)}))
        return
    # Only the JSON goes to stdout; Part 1's logs and any library output go to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        from eventai import tracing
        from eventai.rag.pipeline import ask, load_resources

        tracing.init_tracing("agent")
        brief = run_brief(event, attendees, ask_fn=ask, resources=load_resources(),
                          session_id=payload.get("session_id") or f"part2-{event.event_id}")
        tracing.flush()
    print(json.dumps(brief))


if __name__ == "__main__":
    main()
