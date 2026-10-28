"""One time: put the seed event and the RSVP emails into the Google demo account (CLAUDE.md 10.5, 10.7).

    python seed/seed_google.py            # sign in as the demo account in the browser the first time
    python seed/seed_google.py --dry-run  # show what it would create, with no sign-in
    python seed/seed_google.py --late     # the watcher demo (D18): insert only the late RSVP (seed/late_rsvp.yaml)
    python seed/seed_google.py --noise    # insert only the emails that are not RSVPs (seed/noise_emails.yaml, D19)

It has its own token (token_seed.json) with the write scopes; the agent never uses them. It sends nothing:
the event is created with sendUpdates="none", and the emails are inserted into the inbox, not sent.
A second run is safe: it updates the event by its ID and skips each email whose Message-ID is there.
"""

import argparse
import base64
import sys
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so that "python seed/seed_google.py" finds the eventai package

import yaml  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

from eventai.agent.schema import Email, Event  # noqa: E402
from eventai.agent.tools.google_auth import SEED_SCOPES, build_service, execute, load_credentials  # noqa: E402
from eventai.agent.tools.seed_files import SEED_DIR, load_emails, load_event  # noqa: E402
from eventai.config import load_settings  # noqa: E402

SEED_TOKEN = ROOT / "token_seed.json"
LATE_EMAILS = SEED_DIR / "late_rsvp.yaml"
NOISE_EMAILS = SEED_DIR / "noise_emails.yaml"


def time_zone(path: Path = SEED_DIR / "event.yaml") -> str:
    return yaml.safe_load(path.read_text()).get("time_zone", "Europe/London")


def event_body(event: Event, zone: str) -> dict:
    return {
        "id": event.event_id,
        "summary": event.summary,
        "description": event.description,
        "start": {"dateTime": event.start.isoformat(), "timeZone": zone},
        "end": {"dateTime": (event.end or event.start).isoformat(), "timeZone": zone},
        "attendees": [{"email": i.email, "displayName": i.name} for i in event.invitees],
        "guestsCanSeeOtherGuests": False,
    }


def raw_message(email: Email, to: str) -> str:
    """The email as Gmail stores it. The Message-ID keeps the seed key, so the scorer can match the record."""
    message = EmailMessage()
    message["From"] = f"{email.sender_name} <{email.sender_email}>" if email.sender_name else email.sender_email
    message["To"] = to
    message["Subject"] = email.subject
    message["Date"] = format_datetime(email.date)
    message["Message-ID"] = email.rfc_message_id
    message.set_content(email.body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def seed_event(calendar, event: Event, zone: str) -> str:
    body = event_body(event, zone)
    try:
        calendar.events().get(calendarId="primary", eventId=event.event_id).execute()
    except HttpError as err:
        if err.resp.status != 404:
            raise
        execute(calendar.events().insert(calendarId="primary", body=body, sendUpdates="none"), "create the event")
        return "created"
    # The event is there (perhaps deleted earlier, which keeps its ID): make it current and confirmed.
    execute(calendar.events().update(calendarId="primary", eventId=event.event_id, sendUpdates="none",
                                     body={**body, "status": "confirmed"}), "update the event")
    return "updated"


def seed_emails(gmail, emails: list[Email], to: str) -> tuple[int, int]:
    inserted = skipped = 0
    for email in emails:
        query = f"rfc822msgid:{email.rfc_message_id.strip('<>')}"
        if execute(gmail.users().messages().list(userId="me", q=query), f"find {email.key}").get("messages"):
            skipped += 1
            continue
        body = {"raw": raw_message(email, to), "labelIds": ["INBOX", "UNREAD"]}
        execute(gmail.users().messages().insert(userId="me", internalDateSource="dateHeader", body=body),
                f"insert {email.key}")
        inserted += 1
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show what it would create, with no sign-in")
    extra = parser.add_mutually_exclusive_group()
    extra.add_argument("--late", action="store_true", help="insert only the late RSVP, for the watcher demo")
    extra.add_argument("--noise", action="store_true", help="insert only the emails that are not RSVPs")
    args = parser.parse_args()
    event, zone = load_event(), time_zone()
    emails = load_emails(LATE_EMAILS if args.late else NOISE_EMAILS if args.noise else SEED_DIR / "rsvp_emails.yaml")
    if args.dry_run:
        print(f"Event {event.event_id}: {event.summary}, {event.start:%a %d %b %Y %H:%M} {zone}, "
              f"{len(event.invitees)} invitees, no invitations sent")
        for email in emails:
            print(f"  email {email.key}: {email.sender_email} | {email.subject} | {email.date:%d %b %H:%M}")
        return
    settings = load_settings()
    credentials = load_credentials(ROOT / settings.google_client_secret_file, SEED_TOKEN, SEED_SCOPES)
    calendar = build_service("calendar", "v3", credentials)
    gmail = build_service("gmail", "v1", credentials)
    to = execute(gmail.users().getProfile(userId="me"), "read the profile")["emailAddress"]
    print(f"Signed in as {to}.")
    if not (args.late or args.noise):  # the extra emails need only the inbox
        print(f"Event {event.event_id}: {seed_event(calendar, event, zone)} (no invitations sent).")
    inserted, skipped = seed_emails(gmail, emails, to)
    print(f"{'Other' if args.noise else 'RSVP'} emails: {inserted} inserted, {skipped} already there.")


if __name__ == "__main__":
    main()
