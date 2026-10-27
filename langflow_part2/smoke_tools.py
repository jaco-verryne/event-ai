"""Smoke test of the three agent tools inside Langflow: each one as the Agent sees it (a toolkit)."""

import asyncio

from event_ai.company_search import CompanySearch
from event_ai.crm_lookup import CrmLookup
from event_ai.invitee_lookup import InviteeLookup


async def main() -> None:
    cases = [(CrmLookup(), "sam.okoro@saltmere.example"), (InviteeLookup(), "Tom Price"),
             (CompanySearch(), "Saltmere Freight PLC")]
    for component, query in cases:
        tool = (await component.to_toolkit())[0]
        result = await tool.ainvoke({"query": query})
        print(f"{tool.name}({query!r}) -> {str(getattr(result, 'text', result))[:140]}")


asyncio.run(main())
