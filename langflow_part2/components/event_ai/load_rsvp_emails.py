"""Langflow component: the RSVP emails for the event (step 2)."""

from lfx.custom import Component
from lfx.io import HandleInput, Output
from lfx.schema import DataFrame

from eventai.agent.schema import Event
from eventai.agent.tools import seed_files


class LoadRsvpEmails(Component):
    display_name = "Load RSVP Emails"
    description = "Gets the RSVP emails for the event, from Gmail or from the seed files (the same source as the event)."
    icon = "mail"
    name = "LoadRsvpEmails"

    inputs = [HandleInput(name="event", display_name="Event", input_types=["Data", "JSON"], required=True)]
    outputs = [Output(name="emails", display_name="Emails", method="load_emails")]

    def load_emails(self) -> DataFrame:
        payload = self.event.data
        if payload.get("source") == "google":
            from eventai.agent.tools import gmail, google_auth

            service = google_auth.build_service("gmail", "v1", google_auth.agent_credentials())
            emails = gmail.list_rsvp_emails(service, Event.model_validate(payload))
        else:
            emails = seed_files.load_emails(event_id=payload["event_id"])
        self.status = f"{len(emails)} emails"
        return DataFrame([{**e.model_dump(mode="json"), "key": e.key, "text": e.text} for e in emails])
