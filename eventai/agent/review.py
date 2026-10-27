"""The agent step around the LLM (D12): what the agent sees for each flagged record, and the code check
of its decisions. Framework-independent: the Langflow Agent sits between these two functions.
"""

from pydantic import BaseModel

from eventai.agent import checks
from eventai.agent.schema import FIELDS, Attendee, AuditEntry, CrmContact, Email, Event, FieldValue

ACTIONS = ("use_value", "keep", "human_review")

AGENT_INSTRUCTIONS = """You resolve one flag on one attendee record of a company event.
First call the CRM lookup tool with the attendee's email address. Use the invitee lookup tool for an invitation
question, and the company search tool for a company question. Make at most 3 tool calls.

Then decide the flag:
- use_value: replace the field with a value that a tool result or a source email shows. Copy the value exactly.
- keep: the current value is correct.
- human_review: the evidence does not settle the flag, or a person must decide (for example a substitute guest).
Never invent a value. Give the source of the value (for example crm.csv#C007) and one sentence as the reason."""

_FLAG_FIELDS = {
    "name_differs_from_crm": "full_name", "company_differs_from_crm": "company",
    "email_differs_from_crm": "email", "phone_differs_from_crm": "phone", "phone_invalid": "phone",
    "email_invalid": "email", "attendance_unclear": "attending", "company_not_active": "company_number",
}


class Decision(BaseModel):
    attendee_id: str
    flag: str
    action: str
    value: str | None = None
    source: str | None = None
    reason: str = ""


def flag_field(flag: str) -> str | None:
    """The field that a flag is about; None for a flag on the whole record (not_invited)."""
    if flag.startswith("not_in_source:"):
        return flag.split(":", 1)[1]
    for suffix in ("_conflict", "_absent"):
        if flag.endswith(suffix) and flag.removesuffix(suffix) in FIELDS:
            return flag.removesuffix(suffix)
    return _FLAG_FIELDS.get(flag)


def prompt_text(attendee: Attendee, flag: str, emails: list[Email]) -> str:
    field = flag_field(flag)
    lines = [f"Record {attendee.attendee_id}. Flag: {flag}" + (f" on the field {field}." if field else "."),
             "", "Fields (value | status | source | note):"]
    for name in FIELDS:
        fv = attendee.field(name)
        note = f" | {fv.note}" if fv.note else ""
        lines.append(f"- {name}: {fv.value or '(absent)'} | {fv.status} | {fv.source or '-'}{note}")
    lines += ["", "Source emails:"]
    lines += [f"--- {e.source}\n{e.text}" for e in emails]
    lines += ["", f"Decide the flag {flag} for the record {attendee.attendee_id}."]
    return "\n".join(lines)


def review_items(attendees: list[Attendee], emails: list[Email]) -> list[dict[str, str]]:
    """One item for each review flag of each record; info flags need no decision."""
    by_key = {e.key: e for e in emails}
    items = []
    for a in attendees:
        record_emails = [by_key[k] for k in a.source_keys if k in by_key]
        for flag in a.flags:
            if flag in checks.INFO_FLAGS:
                continue
            items.append({"attendee_id": a.attendee_id, "flag": flag, "field": flag_field(flag) or "",
                          "text": prompt_text(a, flag, record_emails)})
    return items


_NORMALIZE = {"full_name": checks.normalize_name, "email": checks.normalize_email,
              "company": checks.normalize_company, "phone": lambda v: checks.normalize_phone(v)[0]}


def _evidence_source(field: str, value: str, attendee: Attendee, emails: list[Email],
                     crm: list[CrmContact], event: Event) -> str | None:
    """Where the evidence shows this value: the CRM row, a source email, or the invitee list."""
    contact = next((c for c in crm if c.contact_id == attendee.crm_id), None)
    crm_value = getattr(contact, field, None) if contact else None
    if crm_value and checks.value_key(field, crm_value) == checks.value_key(field, value):
        return contact.source
    for email in emails:
        if checks.grounded(field, value, email.text):
            return email.source
    if field == "email" and value.lower() in {i.email.lower() for i in event.invitees}:
        return "calendar:invitees"
    return None


def apply_decisions(attendees: list[Attendee], decisions: list[Decision], *, emails: list[Email],
                    crm: list[CrmContact], event: Event) -> tuple[list[Attendee], list[AuditEntry]]:
    """Apply each decision that passes the code check; send every other flag to human review."""
    decided = {(d.attendee_id, d.flag): d for d in decisions}
    by_key = {e.key: e for e in emails}
    out, audit = [], []
    for attendee in attendees:
        a = attendee.model_copy(deep=True)
        record_emails = [by_key[k] for k in a.source_keys if k in by_key]
        for flag in [f for f in a.flags if f not in checks.INFO_FLAGS]:
            d = decided.get((a.attendee_id, flag))
            field = flag_field(flag)
            action, note, before, after, source = "human_review", None, None, None, None
            if d is None:
                note = "no decision from the agent"
            elif d.action not in ACTIONS:
                note = f"the agent gave an unknown action {d.action!r}"
            elif d.action == "use_value":
                if not field or not d.value:
                    note = "use_value needs a field and a value"
                else:
                    value = _NORMALIZE.get(field, str.strip)(d.value)
                    source = _evidence_source(field, value, a, record_emails, crm, event)
                    if source is None:
                        note = f"value not in evidence: {d.value!r}"
                    else:
                        action, before, after = "use_value", a.field(field).value, value
                        setattr(a, field, FieldValue(value=value, status="corrected", source=source,
                                                     note=f"agent: {d.reason} (was {before!r})"))
            else:
                action = d.action
            reason = d.reason if d else None
            a.resolutions.append(f"{flag}:{action}")
            audit.append(AuditEntry(step="resolve", action=action, attendee_id=a.attendee_id, field=field,
                                    before=before, after=after, source=source,
                                    note="; ".join(filter(None, [reason, note])) or None))
        out.append(a)
    return out, audit
