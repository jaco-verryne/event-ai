"""The agent's read-only lookup tools (D12). Each returns plain rows, so a tool result is JSON text:
an agent reads the printed form of a tool result, and a printed table can hide columns (spike, 27 Oct)."""

from rapidfuzz import fuzz

from eventai.agent.checks import company_key, name_key
from eventai.agent.schema import CrmContact, Event
from eventai.agent.tools import ToolError

NAME_MIN = 80


def crm_lookup(query: str, crm: list[CrmContact]) -> list[dict]:
    """CRM contacts by email address (exact), or by name or company (fuzzy)."""
    q = query.strip().lower()
    if not q:
        return []
    if "@" in q:
        hits = [c for c in crm if c.email.lower() == q]
    else:
        hits = [c for c in crm if fuzz.token_sort_ratio(name_key(c.full_name), name_key(q)) >= NAME_MIN
                or (c.company and company_key(q) and company_key(q) in company_key(c.company))]
    return [{**c.model_dump(), "source": c.source} for c in hits]


def invitee_lookup(query: str, event: Event) -> list[dict]:
    """Invitees by email address (exact) or by name (fuzzy)."""
    q = query.strip().lower()
    hits = [i for i in event.invitees
            if i.email.lower() == q or (i.name and fuzz.token_sort_ratio(name_key(i.name), name_key(q)) >= NAME_MIN)]
    return [{"email": i.email, "name": i.name, "source": "calendar:invitees"} for i in hits]


def company_search(query: str, check) -> dict:
    """The register result for one firm name; a tool failure is a result too, so the agent can go on."""
    try:
        result = check(query)
    except ToolError as err:
        return {"error": str(err)}
    return {"found": result.found, "number": result.number, "name": result.name, "status": result.status,
            "source": f"companies_house:{result.number}" if result.found else "companies_house:search"}
