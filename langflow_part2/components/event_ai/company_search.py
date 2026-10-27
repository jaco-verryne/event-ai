"""Langflow component, an agent tool: a firm on the UK Companies House register."""

import json

from lfx.custom import Component
from lfx.io import MessageTextInput, Output
from lfx.schema import Message

from eventai.agent.lookups import company_search
from eventai.agent.tools.companies_house import CompaniesHouse
from eventai.config import load_settings


class CompanySearch(Component):
    display_name = "Company Search"
    description = "Looks up a firm on the UK Companies House register. Returns found, number, name and status as JSON."
    icon = "building"
    name = "CompanySearch"

    inputs = [MessageTextInput(name="query", display_name="Company name", tool_mode=True, required=True)]
    outputs = [Output(name="company_search", display_name="Result", method="company_search")]

    def company_search(self) -> Message:
        result = company_search(str(self.query), CompaniesHouse(load_settings().companies_house_api_key).check)
        self.status = json.dumps(result)
        return Message(text=json.dumps(result))
