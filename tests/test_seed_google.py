"""seed/seed_google.py, offline: the event body, the raw emails, and a safe second run."""

import base64
import email as email_lib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httplib2
import pytest
from googleapiclient.errors import HttpError

from eventai.agent.tools.seed_files import load_emails, load_event

spec = importlib.util.spec_from_file_location(
    "seed_google", Path(__file__).resolve().parent.parent / "seed" / "seed_google.py"
)
seed_google = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_google)


class Request:
    def __init__(self, result=None, error=None, log=None, name=None, kwargs=None):
        self.result, self.error = result, error
        if log is not None:
            log.append((name, kwargs))

    def execute(self):
        if self.error:
            raise self.error
        return self.result


def not_found():
    return HttpError(httplib2.Response({"status": "404"}), b"not found")


def test_event_body_sends_no_invitations_and_keeps_the_venue():
    body = seed_google.event_body(load_event(), "Europe/London")
    assert body["id"] == "partnersummit2026"
    assert "Venue: V113" in body["description"]
    assert len(body["attendees"]) == 12 and body["start"]["timeZone"] == "Europe/London"


def test_raw_message_keeps_the_headers():
    first = load_emails()[0]
    raw = seed_google.raw_message(first, "demo@gmail.example")
    parsed = email_lib.message_from_bytes(base64.urlsafe_b64decode(raw))
    assert parsed["Message-ID"] == "<e01.partnersummit2026@seed.example>"
    assert parsed["From"] == "Amelia Hart <amelia.hart@tallowmere.example>"
    assert parsed["Date"] == "Mon, 02 Nov 2026 09:15:00 +0000"
    assert "I will attend" in parsed.get_payload(decode=True).decode()


@pytest.mark.parametrize("exists, expected", [(False, "created"), (True, "updated")])
def test_seed_event_creates_or_updates(exists, expected):
    log = []
    events = SimpleNamespace(
        get=lambda **kw: Request(result={"id": "partnersummit2026"} if exists else None,
                                 error=None if exists else not_found()),
        insert=lambda **kw: Request({}, log=log, name="insert", kwargs=kw),
        update=lambda **kw: Request({}, log=log, name="update", kwargs=kw),
    )
    calendar = SimpleNamespace(events=lambda: events)
    assert seed_google.seed_event(calendar, load_event(), "Europe/London") == expected
    name, kwargs = log[0]
    assert name == ("insert" if expected == "created" else "update")
    assert kwargs["sendUpdates"] == "none"


def test_seed_emails_skips_the_emails_already_there():
    inserted_bodies = []
    there = {"e01.partnersummit2026@seed.example"}
    messages = SimpleNamespace(
        list=lambda userId, q: Request({"messages": [{"id": "x"}]} if q.split(":", 1)[1] in there else {}),
        insert=lambda userId, internalDateSource, body: Request({}, log=inserted_bodies, name="insert", kwargs=body),
    )
    gmail = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: messages))
    assert seed_google.seed_emails(gmail, load_emails(), "demo@gmail.example") == (12, 1)
    assert all(kwargs["labelIds"] == ["INBOX", "UNREAD"] for _, kwargs in inserted_bodies)


def test_the_late_rsvp_is_a_separate_invited_reply_that_the_search_finds():
    from eventai.agent.tools.gmail import rsvp_query
    from eventai.agent.tools.seed_files import SEED_DIR, load_crm

    late = load_emails(seed_google.LATE_EMAILS)
    assert [e.key for e in late] == ["e14"]
    assert "e14" not in {e.key for e in load_emails()}  # the seed-file source stays at 13 emails
    event = load_event()
    assert late[0].sender_email in {i.email for i in event.invitees}
    assert late[0].sender_email not in {c.email for c in load_crm()}
    assert rsvp_query(event).strip('"').lower() in f"{late[0].subject} {late[0].body}".lower()
    expected = (SEED_DIR / "expected_late.csv").read_text()
    assert "e14,Ravi Desai,ravi.desai@brackenlow.example,+441614960714" in expected
