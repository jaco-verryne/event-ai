"""The seed files as a source. They return the same models as the Calendar and Gmail tools, so the
offline run (--source seed), the tests and seed_google.py all read one copy of the data."""

import csv
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

import yaml

from eventai.agent.schema import CrmContact, Email, Event, Invitee
from eventai.config import ROOT

SEED_DIR = ROOT / "seed"
VENUES_CSV = ROOT / "data" / "venues.csv"


def load_event(path: Path = SEED_DIR / "event.yaml") -> Event:
    raw = yaml.safe_load(path.read_text())
    return Event(
        event_id=raw["event_id"],
        summary=raw["summary"],
        start=datetime.fromisoformat(raw["start"]),
        end=datetime.fromisoformat(raw["end"]) if raw.get("end") else None,
        description=raw.get("description", ""),
        venue_id=venue_id_from(raw.get("description", "")),
        invitees=[Invitee(**i) for i in raw.get("invitees", [])],
    )


def seed_message_id(key: str, event_id: str) -> str:
    return f"<{key}.{event_id}@seed.example>"


def load_emails(path: Path = SEED_DIR / "rsvp_emails.yaml", event_id: str = "partnersummit2026") -> list[Email]:
    emails = []
    for raw in yaml.safe_load(path.read_text()):
        name, address = parseaddr(raw["from"])
        emails.append(Email(
            message_id=raw["key"],
            rfc_message_id=seed_message_id(raw["key"], event_id),
            source=f"seed:{raw['key']}",
            sender_name=name or None,
            sender_email=address,
            date=datetime.fromisoformat(raw["date"]),
            subject=raw["subject"],
            body=raw["body"],
        ))
    return emails


def load_crm(path: Path = SEED_DIR / "crm.csv") -> list[CrmContact]:
    with path.open(newline="") as f:
        return [CrmContact(**{k: (v or None) for k, v in row.items()}) for row in csv.DictReader(f)]


def venue_id_from(description: str) -> str | None:
    """The venue ID from a line such as 'Venue: V113' in the event description."""
    for line in description.splitlines():
        label, _, value = line.partition(":")
        if label.strip().lower() == "venue" and value.strip():
            return value.strip().split()[0]
    return None


def venue_row(venue_id: str | None, path: Path = VENUES_CSV) -> dict[str, str] | None:
    """The venue's row in the Part 1 venues file: the link between the two parts."""
    if not venue_id:
        return None
    with path.open(newline="") as f:
        return next((row for row in csv.DictReader(f) if row["venue_id"] == venue_id), None)


def venue_capacity(venue_id: str | None, path: Path = VENUES_CSV) -> int | None:
    row = venue_row(venue_id, path)
    return int(row["seated_capacity"]) if row else None
