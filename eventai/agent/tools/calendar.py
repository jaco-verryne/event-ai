"""Calendar tool: one event, its invitees and its venue ID, with the read-only scope."""

from datetime import datetime

from eventai.agent.schema import Event, Invitee
from eventai.agent.tools.google_auth import execute
from eventai.agent.tools.seed_files import venue_id_from


def get_event(service, event_id: str, calendar_id: str = "primary") -> Event:
    raw = execute(service.events().get(calendarId=calendar_id, eventId=event_id), f"Calendar event {event_id}")
    return event_from_api(raw)


def _when(value: dict | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.get("dateTime") or value["date"])


def event_from_api(raw: dict) -> Event:
    description = raw.get("description", "")
    # The organizer (the demo account) and room resources are not invitees.
    invitees = [Invitee(email=a["email"], name=a.get("displayName"))
                for a in raw.get("attendees", []) if not a.get("organizer") and not a.get("resource")]
    return Event(
        event_id=raw["id"],
        summary=raw.get("summary", ""),
        start=_when(raw.get("start")),
        end=_when(raw.get("end")),
        description=description,
        venue_id=venue_id_from(description),
        invitees=invitees,
    )
