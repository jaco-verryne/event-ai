"""Langflow component: the event, its invitees and its venue ID (step 1)."""

from lfx.custom import Component
from lfx.io import DropdownInput, MessageTextInput, Output
from lfx.schema import Data

from eventai.agent.tools import seed_files


class LoadEvent(Component):
    display_name = "Load Event"
    description = "Gets the event, its invitees and its venue ID, from Google Calendar or from the seed files."
    icon = "calendar"
    name = "LoadEvent"

    inputs = [
        MessageTextInput(name="event_id", display_name="Event ID", required=True,
                         info="Connect the Chat Input. Type the event ID, for example partnersummit2026."),
        DropdownInput(name="source", display_name="Source", options=["seed", "google"], value="seed",
                      info="seed: the files in seed/. google: Calendar and Gmail of the demo account (read-only)."),
    ]
    outputs = [Output(name="event", display_name="Event", method="load_event")]

    def load_event(self) -> Data:
        event_id = str(self.event_id).strip()
        if self.source == "google":
            from eventai.agent.tools import calendar, google_auth

            service = google_auth.build_service("calendar", "v3", google_auth.agent_credentials())
            event = calendar.get_event(service, event_id)
        else:
            event = seed_files.load_event()
            if event.event_id != event_id:
                raise ValueError(f"The seed event is {event.event_id!r}, not {event_id!r}.")
        self.status = f"{event.summary}: {len(event.invitees)} invitees, venue {event.venue_id}"
        return Data(data={**event.model_dump(mode="json"), "source": self.source})
