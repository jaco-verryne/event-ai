"""Langflow component, an agent tool: is a person on the invitee list of the event."""

import json

from lfx.custom import Component
from lfx.io import HandleInput, MessageTextInput, Output
from lfx.schema import Message

from eventai.agent.lookups import invitee_lookup
from eventai.agent.schema import Event


class InviteeLookup(Component):
    display_name = "Invitee Lookup"
    description = "Finds invitees of the event by email address or by name. Returns the matching invitees as JSON."
    icon = "users"
    name = "InviteeLookup"

    inputs = [
        MessageTextInput(name="query", display_name="Email or name", tool_mode=True, required=True),
        HandleInput(name="event", display_name="Event", input_types=["Data", "JSON"], required=True),
    ]
    outputs = [Output(name="invitee_lookup", display_name="Invitees", method="invitee_lookup")]

    def invitee_lookup(self) -> Message:
        rows = invitee_lookup(str(self.query), Event.model_validate(self.event.data))
        self.status = f"{len(rows)} invitees for {self.query!r}"
        return Message(text=json.dumps(rows))
