"""Gmail tool: the RSVP emails for one event, with the read-only scope."""

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime

from eventai.agent.schema import Email, Event
from eventai.agent.tools.google_auth import execute


def rsvp_query(event: Event) -> str:
    """Gmail search: each RSVP names the event in its subject or body, but a reply seldom repeats the
    year (seed email e07: "the Northern Partners Summit"), so the search leaves out a final year."""
    return f'"{re.sub(r"\s+(19|20)\d{2}$", "", event.summary.strip())}"'


def rsvp_message_ids(service, event: Event, query: str | None = None, limit: int = 200) -> list[str]:
    """The IDs of the event's RSVP emails, with no message bodies. The watcher compares these."""
    ids, token = [], None
    while len(ids) < limit:
        page = execute(service.users().messages().list(userId="me", q=query or rsvp_query(event), pageToken=token,
                                                       maxResults=100), "Gmail search")
        ids += [m["id"] for m in page.get("messages", [])]
        token = page.get("nextPageToken")
        if not token:
            break
    return ids[:limit]


def list_rsvp_emails(service, event: Event, query: str | None = None, limit: int = 200) -> list[Email]:
    emails = [email_from_api(execute(service.users().messages().get(userId="me", id=i, format="full"),
                                     f"Gmail message {i}"))
              for i in rsvp_message_ids(service, event, query, limit)]
    return sorted(emails, key=lambda e: e.date)


def email_from_api(raw: dict) -> Email:
    headers = {h["name"].lower(): h["value"] for h in raw["payload"].get("headers", [])}
    name, address = parseaddr(headers.get("from", ""))
    if "date" in headers:
        date = parsedate_to_datetime(headers["date"])
    else:
        date = datetime.fromtimestamp(int(raw["internalDate"]) / 1000, tz=timezone.utc)
    return Email(
        message_id=raw["id"],
        rfc_message_id=headers.get("message-id", ""),
        source=f"gmail:{raw['id']}",
        sender_name=name or None,
        sender_email=address,
        date=date,
        subject=headers.get("subject", ""),
        body=plain_text(raw["payload"]),
    )


def _parts(part: dict):
    yield part
    for sub in part.get("parts", []):
        yield from _parts(sub)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def plain_text(payload: dict) -> str:
    """The text/plain part; else the text/html part without its tags."""
    parts = list(_parts(payload))
    for mime in ("text/plain", "text/html"):
        for part in parts:
            data = part.get("body", {}).get("data")
            if part.get("mimeType") == mime and data:
                text = _decode(data)
                return text if mime == "text/plain" else html.unescape(re.sub(r"<[^>]+>", " ", text))
    return ""
