"""Langflow component, an agent tool: is a person on the invitee list of the event.

It has no Event input on purpose: Langflow's Loop re-runs every component that its body depends on, so
an input from Load Event would re-run the start of the flow for each flagged record. It reads the event
that Load Event loaded for this run (eventai.agent.flow_io)."""

import json

from lfx.custom import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message

from eventai.agent.flow_io import remembered_event
from eventai.agent.lookups import invitee_lookup


class InviteeLookup(Component):
    display_name = "Invitee Lookup"
    description = "Finds invitees of the event by email address or by name. Returns the matching invitees as JSON."
    icon = "users"
    name = "InviteeLookup"

    inputs = [MessageTextInput(name="query", display_name="Email or name", tool_mode=True, required=True)]
    outputs = [Output(name="invitee_lookup", display_name="Invitees", method="invitee_lookup")]

    def invitee_lookup(self) -> Message:
        rows = invitee_lookup(str(self.query), remembered_event())
        self.status = f"{len(rows)} invitees for {self.query!r}"
        return Message(text=json.dumps(rows))
