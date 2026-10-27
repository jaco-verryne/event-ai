"""Langflow component, an agent tool: CRM contacts by email, name or company."""

import json

from lfx.custom import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message

from eventai.agent.lookups import crm_lookup
from eventai.agent.tools import seed_files


class CrmLookup(Component):
    display_name = "CRM Lookup"
    description = "Finds CRM contacts by email address, by name or by company. Returns the matching rows as JSON."
    icon = "contact"
    name = "CrmLookup"

    inputs = [MessageTextInput(name="query", display_name="Email, name or company", tool_mode=True, required=True)]
    outputs = [Output(name="crm_lookup", display_name="Rows", method="crm_lookup")]

    def crm_lookup(self) -> Message:
        rows = crm_lookup(str(self.query), seed_files.load_crm())
        self.status = f"{len(rows)} rows for {self.query!r}"
        return Message(text=json.dumps(rows))
