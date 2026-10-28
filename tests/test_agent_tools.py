"""Part 2 tools, offline: fake Google requests and a fake requests session."""

import base64
from datetime import datetime, timezone
from types import SimpleNamespace

import httplib2
import pytest
import requests
from googleapiclient.errors import HttpError
from tenacity import wait_none

from eventai.agent import tools
from eventai.agent.tools import ToolError
from eventai.agent.tools.calendar import event_from_api, get_event, upcoming_events
from eventai.agent.tools.companies_house import CompaniesHouse
from eventai.agent.tools.gmail import email_from_api, list_rsvp_emails, rsvp_message_ids, rsvp_query
from eventai.agent.tools.google_auth import execute, load_credentials


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(tools, "WAIT", wait_none())


def http_error(status):
    return HttpError(httplib2.Response({"status": str(status)}), b"error")


class FakeRequest:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def execute(self):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


# Google request execution

def test_execute_retries_a_rate_limit_then_succeeds():
    request = FakeRequest(http_error(429), {"ok": True})
    assert execute(request, "test") == {"ok": True}
    assert request.calls == 2


def test_execute_gives_up_after_three_tries():
    request = FakeRequest(TimeoutError("slow"), TimeoutError("slow"), TimeoutError("slow"))
    with pytest.raises(ToolError, match="test failed: slow"):
        execute(request, "test")
    assert request.calls == 3


def test_execute_does_not_retry_a_not_found():
    request = FakeRequest(http_error(404))
    with pytest.raises(ToolError):
        execute(request, "test")
    assert request.calls == 1


def test_sign_in_needs_the_client_secret_file(tmp_path):
    with pytest.raises(ToolError, match="credentials.json is missing"):
        load_credentials(tmp_path / "credentials.json", tmp_path / "token.json", ["scope"])


# Calendar

RAW_EVENT = {
    "id": "partnersummit2026",
    "summary": "Northern Partners Summit 2026",
    "description": "Talks and drinks.\nVenue: V113",
    "start": {"dateTime": "2026-11-26T14:00:00Z"},
    "end": {"dateTime": "2026-11-26T18:00:00Z"},
    "attendees": [
        {"email": "demo@events.example", "organizer": True, "self": True},
        {"email": "amelia.hart@tallowmere.example", "displayName": "Amelia Hart"},
        {"email": "room-1@resource.example", "resource": True},
        {"email": "ravi.desai@brackenlow.example"},
    ],
}


def test_event_from_api():
    event = event_from_api(RAW_EVENT)
    assert event.venue_id == "V113"
    assert [i.email for i in event.invitees] == ["amelia.hart@tallowmere.example", "ravi.desai@brackenlow.example"]
    assert event.invitees[0].name == "Amelia Hart"
    assert event.start.isoformat() == "2026-11-26T14:00:00+00:00"


def test_get_event_calls_the_api_with_the_id():
    seen = {}

    def get(calendarId, eventId):
        seen.update(calendarId=calendarId, eventId=eventId)
        return FakeRequest(RAW_EVENT)

    service = SimpleNamespace(events=lambda: SimpleNamespace(get=get))
    assert get_event(service, "partnersummit2026").event_id == "partnersummit2026"
    assert seen == {"calendarId": "primary", "eventId": "partnersummit2026"}


def test_upcoming_events_keeps_the_events_that_name_a_venue():
    team_lunch = {**RAW_EVENT, "id": "lunch", "description": "No venue here."}
    cancelled = {**RAW_EVENT, "id": "old", "status": "cancelled"}
    pages = [{"items": [team_lunch, RAW_EVENT], "nextPageToken": "t2"}, {"items": [cancelled]}]
    calls = []

    def list_(**kwargs):
        calls.append(kwargs)
        return FakeRequest(pages.pop(0))

    service = SimpleNamespace(events=lambda: SimpleNamespace(list=list_))
    now = datetime(2026, 10, 28, tzinfo=timezone.utc)
    events = upcoming_events(service, days=60, now=now)
    assert [e.event_id for e in events] == ["partnersummit2026"]
    assert calls[0]["timeMin"] == "2026-10-28T00:00:00+00:00"
    assert calls[0]["timeMax"] == "2026-12-27T00:00:00+00:00"
    assert calls[0]["singleEvents"] is True and calls[1]["pageToken"] == "t2"


# Gmail

def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def raw_message(msg_id, body, mime="text/plain"):
    return {
        "id": msg_id,
        "internalDate": "1793600000000",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Sam Okoro <sam.okoro@saltmere.example>"},
                {"name": "Date", "value": "Wed, 04 Nov 2026 08:05:00 +0000"},
                {"name": "Subject", "value": "Re: Invitation: Northern Partners Summit 2026"},
                {"name": "Message-ID", "value": "<e10.partnersummit2026@seed.example>"},
            ],
            "parts": [{"mimeType": mime, "body": {"data": b64(body)}}],
        },
    }


def test_email_from_api_reads_headers_and_the_plain_text():
    email = email_from_api(raw_message("18f2a", "Yes, I will attend.\n\nSam Okoro"))
    assert email.sender_email == "sam.okoro@saltmere.example"
    assert email.sender_name == "Sam Okoro"
    assert email.key == "e10"
    assert email.source == "gmail:18f2a"
    assert email.date.isoformat() == "2026-11-04T08:05:00+00:00"
    assert email.body.startswith("Yes, I will attend.")


def test_email_from_api_falls_back_to_html():
    email = email_from_api(raw_message("18f2b", "<p>Yes, I&#39;ll be there.</p>", mime="text/html"))
    assert email.body.strip() == "Yes, I'll be there."


def test_list_rsvp_emails_pages_through_the_search():
    pages = [{"messages": [{"id": "a"}], "nextPageToken": "t2"}, {"messages": [{"id": "b"}]}]
    queries = []

    def list_(userId, q, pageToken, maxResults):
        queries.append((q, pageToken))
        return FakeRequest(pages.pop(0))

    def get(userId, id, format):
        return FakeRequest(raw_message(id, f"body {id}"))

    messages = SimpleNamespace(list=list_, get=get)
    service = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: messages))
    event = event_from_api(RAW_EVENT)
    emails = list_rsvp_emails(service, event)
    assert [e.message_id for e in emails] == ["a", "b"]
    assert queries == [(rsvp_query(event), None), (rsvp_query(event), "t2")]
    assert rsvp_query(event) == '"Northern Partners Summit"'


def test_rsvp_message_ids_reads_no_message_bodies():
    pages = [{"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t2"}, {"messages": [{"id": "c"}]}]
    messages = SimpleNamespace(list=lambda **kw: FakeRequest(pages.pop(0)),
                               get=lambda **kw: pytest.fail("the watcher must not fetch bodies"))
    service = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: messages))
    assert rsvp_message_ids(service, event_from_api(RAW_EVENT)) == ["a", "b", "c"]


# Companies House

class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append({"url": url, "params": params, "auth": auth, "timeout": timeout})
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def test_no_key_is_a_tool_error():
    with pytest.raises(ToolError, match="no Companies House API key"):
        CompaniesHouse(None, session=FakeSession()).check("Acme Ltd")


def test_not_on_the_register():
    session = FakeSession(FakeResponse(200, {"items": [{"title": "ACME ROCKETS LIMITED", "company_number": "1"}]}))
    result = CompaniesHouse("key", session=session).check("Quillmere Events Ltd")
    assert not result.found
    assert session.calls[0]["auth"] == ("key", "")
    assert session.calls[0]["timeout"] == 10


def test_found_reads_the_status_from_the_profile():
    session = FakeSession(
        FakeResponse(200, {"items": [{"title": "QUILLMERE EVENTS LIMITED", "company_number": "01234567"}]}),
        FakeResponse(200, {"company_name": "QUILLMERE EVENTS LIMITED", "company_status": "dissolved"}),
    )
    result = CompaniesHouse("key", session=session).check("Quillmere Events Ltd")
    assert result.found and result.number == "01234567" and result.status == "dissolved"
    assert session.calls[1]["url"].endswith("/company/01234567")


def test_cache_makes_one_request_for_a_repeated_name():
    session = FakeSession(FakeResponse(200, {"items": []}))
    house = CompaniesHouse("key", session=session)
    house.check("Tallowmere Foods Ltd")
    house.check("Tallowmere Foods Ltd")
    assert house.requests_sent == 1


def test_rate_limit_is_retried():
    session = FakeSession(FakeResponse(429), FakeResponse(200, {"items": []}))
    house = CompaniesHouse("key", session=session)
    assert not house.check("Tallowmere Foods Ltd").found
    assert house.requests_sent == 2


def test_timeouts_become_a_tool_error():
    session = FakeSession(*[requests.Timeout("slow")] * 3)
    with pytest.raises(ToolError, match="slow"):
        CompaniesHouse("key", session=session).check("Tallowmere Foods Ltd")
    assert len(session.calls) == 3


def test_a_client_error_is_not_retried():
    session = FakeSession(FakeResponse(401))
    with pytest.raises(ToolError, match="HTTP 401"):
        CompaniesHouse("bad-key", session=session).check("Tallowmere Foods Ltd")
    assert len(session.calls) == 1


def test_the_gmail_search_finds_every_seed_email():
    from eventai.agent.tools.seed_files import load_emails, load_event

    phrase = rsvp_query(load_event()).strip('"').lower()
    assert all(phrase in f"{e.subject} {e.body}".lower() for e in load_emails())
