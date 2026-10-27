"""Part 2 data models: what the tools return, what the LLM extracts, and what the run writes."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

FieldStatus = Literal["verified", "corrected", "absent", "conflict"]

# The fields of one attendee, in output order. attending is "yes", "no" or absent (unclear).
FIELDS = ("full_name", "email", "phone", "company", "company_number", "job_title", "dietary_needs", "attending")
# The fields that the LLM extracts from one email.
EXTRACTED_FIELDS = ("full_name", "email", "phone", "company", "job_title", "dietary_needs", "attending")

_SEED_KEY = re.compile(r"<(e\d+)\.")


class Invitee(BaseModel):
    email: str
    name: str | None = None


class Event(BaseModel):
    event_id: str
    summary: str
    start: datetime
    end: datetime | None = None
    description: str = ""
    venue_id: str | None = None
    invitees: list[Invitee] = []


class Email(BaseModel):
    message_id: str          # the Gmail message ID, or the seed key offline
    rfc_message_id: str      # the Message-ID header; it holds the seed key in both sources
    source: str              # "gmail:<message_id>" or "seed:<key>"
    sender_name: str | None
    sender_email: str
    date: datetime
    subject: str
    body: str

    @property
    def key(self) -> str:
        """The seed key (e05) when the Message-ID has one, so the scorer can match any source."""
        match = _SEED_KEY.search(self.rfc_message_id)
        return match.group(1) if match else self.message_id

    @property
    def text(self) -> str:
        """What the LLM reads and what the grounding check searches: the headers and the body."""
        sender = f"{self.sender_name} <{self.sender_email}>" if self.sender_name else self.sender_email
        return f"From: {sender}\nDate: {self.date.isoformat()}\nSubject: {self.subject}\n\n{self.body}"


class CrmContact(BaseModel):
    contact_id: str
    full_name: str
    email: str
    phone: str | None = None
    company: str | None = None
    job_title: str | None = None

    @property
    def source(self) -> str:
        return f"crm.csv#{self.contact_id}"


class ExtractedRsvp(BaseModel):
    full_name: str | None
    email: str | None
    phone: str | None
    company: str | None
    job_title: str | None
    dietary_needs: str | None
    attending: bool | None


class FieldValue(BaseModel):
    value: str | None
    status: FieldStatus
    source: str              # "gmail:<id>", "crm.csv#C014" or "companies_house:<number>"; "+" joins several
    note: str | None = None


def absent(note: str | None = None) -> FieldValue:
    return FieldValue(value=None, status="absent", source="", note=note)


class Record(BaseModel):
    """One email after extraction and the code checks, before deduplication."""

    email_key: str
    email_source: str
    date: datetime
    fields: dict[str, FieldValue]
    flags: list[str] = []


class Attendee(BaseModel):
    attendee_id: str
    full_name: FieldValue
    email: FieldValue
    phone: FieldValue
    company: FieldValue
    company_number: FieldValue
    job_title: FieldValue
    dietary_needs: FieldValue
    attending: FieldValue
    flags: list[str] = []
    source_keys: list[str] = []                       # the emails merged into this record
    candidates: dict[str, list[FieldValue]] = {}      # the values of a field in conflict
    crm_id: str | None = None
    resolutions: list[str] = []                       # "<flag>:<action>", set by the agent step

    def field(self, name: str) -> FieldValue:
        return getattr(self, name)


class AuditEntry(BaseModel):
    step: str                    # ground, normalize, dedupe, verify or resolve
    action: str                  # removed, changed, merged, filled, rule, flagged or note
    attendee_id: str | None = None
    email_key: str | None = None
    field: str | None = None
    before: str | None = None
    after: str | None = None
    source: str | None = None
    note: str | None = None
