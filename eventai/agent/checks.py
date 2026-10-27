"""Part 2 code checks: grounding, normalization, deduplication and verification (CLAUDE.md 10.1).

Plain code, so each rule is repeatable and has a unit test. Each change goes to the audit log.
The LLM never runs here: it extracts before these steps and judges the flagged records after them.
"""

import re
from collections.abc import Callable, Iterable

import phonenumbers
from rapidfuzz import fuzz

from eventai.agent.schema import (
    EXTRACTED_FIELDS, Attendee, AuditEntry, CrmContact, Email, Event, ExtractedRsvp, FieldValue, Record, absent,
)
from eventai.agent.tools import ToolError

GROUNDING_MIN = 90       # partial_ratio of a value against its own email
DUPLICATE_NAME_MIN = 88  # token_sort_ratio of two names for a fuzzy duplicate
COMPANY_MIN = 85         # token_sort_ratio of two company names (suffix ignored)
CRM_NAME_MIN = 90        # token_sort_ratio for a CRM match by name and company

# Info flags go to the run report only. Every other flag sends the record to the agent step.
INFO_FLAGS = {"phone_absent", "web_check_failed"}
# A tool failure is not a data defect, so the scorer reports it apart from the precision and recall.
TOOL_FLAGS = {"web_check_failed"}
REQUIRED = ("full_name", "email", "company")
LATEST_WINS = ("dietary_needs", "attending")  # a later email can change these

COMPANY_SUFFIXES = {"ltd": "Ltd", "ltd.": "Ltd", "limited": "Ltd", "plc": "PLC", "p.l.c.": "PLC", "llp": "LLP"}
_SUFFIX_WORDS = {"ltd", "limited", "plc", "llp"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_LIKE = re.compile(r"\+?\d[\d ()\-]*\d")

CompanyCheck = Callable[[str], "object"]  # companies_house.CompaniesHouse.check, or a fake in the tests


# Keys for comparing values

def national_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "0" + digits[2:] if digits.startswith("44") else digits


def name_key(name: str) -> str:
    return " ".join(name.casefold().split())


def company_key(name: str) -> str:
    """Lower case, no punctuation, no suffix: 'Quillmere Events Ltd' and 'Quillmere Events' match."""
    words = re.sub(r"[^\w\s&]", " ", name.lower()).replace("&", " and ").split()
    return " ".join(w for w in words if w not in _SUFFIX_WORDS)


def value_key(field: str, value: str) -> str:
    if field == "company":
        return company_key(value)
    if field == "phone":
        return national_digits(value)
    return name_key(value)


# Grounding

def grounded(field: str, value: str, text: str) -> bool:
    """True when the extracted value appears in its source email (headers and body)."""
    if field == "email":
        return value.strip().lower() in text.lower()
    if field == "phone":
        digits = national_digits(value)
        return bool(digits) and any(national_digits(m) == digits for m in _PHONE_LIKE.findall(text))
    return fuzz.partial_ratio(value.lower(), text.lower()) >= GROUNDING_MIN


def ground(extracted: ExtractedRsvp, email: Email) -> tuple[Record, list[AuditEntry]]:
    """Keep each extracted value that the email supports. Remove the others: no guessing."""
    fields, flags, audit = {}, [], []
    text = email.text
    for field in EXTRACTED_FIELDS:
        raw = getattr(extracted, field)
        if field == "attending":
            fields[field] = absent() if raw is None else FieldValue(
                value="yes" if raw else "no", status="verified", source=email.source)
            continue
        value = (raw or "").strip()
        if not value:
            fields[field] = absent()
        elif grounded(field, value, text):
            fields[field] = FieldValue(value=value, status="verified", source=email.source)
        else:
            fields[field] = absent(note=f"not in the email: {value!r}")
            flags.append(f"not_in_source:{field}")
            audit.append(AuditEntry(step="ground", action="removed", email_key=email.key, field=field,
                                    before=value, source=email.source, note="the value is not in the email"))
    return Record(email_key=email.key, email_source=email.source, date=email.date, fields=fields, flags=flags), audit


# Normalization

def _capitalize(word: str) -> str:
    parts = re.split(r"([-'])", word)
    out = []
    for part in parts:
        if part.lower().startswith("mc") and len(part) > 2:
            out.append("Mc" + part[2:].capitalize())
        else:
            out.append(part.capitalize())
    return "".join(out)


def normalize_name(name: str) -> str:
    """Fix the case only when the whole name is in one case; keep mixed case (McDonald) as written."""
    name = " ".join(name.split())
    if name.islower() or name.isupper():
        name = " ".join(_capitalize(w) for w in name.split())
    return name


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(raw: str) -> tuple[str, bool]:
    """E.164 for a valid number (default region GB). An invalid number keeps its raw value."""
    try:
        number = phonenumbers.parse(raw, "GB")
    except phonenumbers.NumberParseException:
        return raw, False
    if not phonenumbers.is_valid_number(number):
        return raw, False
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164), True


def normalize_company(name: str) -> str:
    words = name.split()
    if words and words[-1].lower() in COMPANY_SUFFIXES:
        words[-1] = COMPANY_SUFFIXES[words[-1].lower()]
    return " ".join(words)


def clean_text(text: str) -> str:
    return " ".join(text.split()).rstrip(".,;:")


_NORMALIZERS = {
    "full_name": normalize_name, "email": normalize_email, "company": normalize_company,
    "job_title": clean_text, "dietary_needs": clean_text,
}


def normalize(record: Record) -> tuple[Record, list[AuditEntry]]:
    fields, flags, audit = dict(record.fields), list(record.flags), []
    for field, fv in record.fields.items():
        if fv.value is None or field == "attending":
            continue
        if field == "phone":
            new, valid = normalize_phone(fv.value)
            if not valid:
                fields[field] = fv.model_copy(update={"status": "conflict", "note": "not a valid UK phone number"})
                flags.append("phone_invalid")
                audit.append(AuditEntry(step="normalize", action="flagged", email_key=record.email_key, field=field,
                                        before=fv.value, note="not a valid UK phone number"))
                continue
        else:
            new = _NORMALIZERS[field](fv.value)
        if new != fv.value:
            fields[field] = fv.model_copy(update={"value": new, "status": "corrected", "note": f"was {fv.value!r}"})
            audit.append(AuditEntry(step="normalize", action="changed", email_key=record.email_key, field=field,
                                    before=fv.value, after=new, source=fv.source))
    return record.model_copy(update={"fields": fields, "flags": flags}), audit


# Deduplication

def _join(sources: Iterable[str]) -> str:
    parts = (p for s in sources if s for p in s.split(" + "))  # a source can already be a joined one
    return " + ".join(dict.fromkeys(parts))


def _same_person(group: list[Record], record: Record) -> bool:
    email = record.fields["email"].value
    if email and any(r.fields["email"].value == email for r in group):
        return True
    name, company = record.fields["full_name"].value, record.fields["company"].value
    if not (name and company):
        return False
    for r in group:
        other_name, other_company = r.fields["full_name"].value, r.fields["company"].value
        if other_name and other_company \
                and fuzz.token_sort_ratio(name_key(name), name_key(other_name)) >= DUPLICATE_NAME_MIN \
                and fuzz.token_sort_ratio(company_key(company), company_key(other_company)) >= COMPANY_MIN:
            return True
    return False


def _merge(attendee_id: str, group: list[Record]) -> tuple[Attendee, list[AuditEntry]]:
    values, candidates, audit = {}, {}, []
    flags = {f for r in group for f in r.flags}
    for field in EXTRACTED_FIELDS:
        present = [r.fields[field] for r in group if r.fields[field].value is not None]
        if not present:
            values[field] = next((r.fields[field] for r in group if r.fields[field].note), absent())
            continue
        if field in LATEST_WINS:
            values[field] = present[-1]  # the group is in date order
            continue
        distinct: dict[str, list[FieldValue]] = {}
        for fv in present:
            distinct.setdefault(value_key(field, fv.value), []).append(fv)
        if len(distinct) == 1:
            same = next(iter(distinct.values()))
            best = max(same, key=lambda fv: len(fv.value))  # the fullest form, e.g. with the company suffix
            status = next((s for s in ("conflict", "corrected") if any(fv.status == s for fv in same)), best.status)
            values[field] = best.model_copy(update={"status": status, "source": _join(fv.source for fv in same)})
        else:
            options = [fvs[0] for fvs in distinct.values()]
            candidates[field] = options
            values[field] = options[0].model_copy(update={
                "status": "conflict", "note": "candidates: " + " | ".join(f"{o.value} ({o.source})" for o in options)})
            flags.add(f"{field}_conflict")
            audit.append(AuditEntry(step="dedupe", action="flagged", attendee_id=attendee_id, field=field,
                                    note=values[field].note))
    if len(group) > 1:
        audit.append(AuditEntry(step="dedupe", action="merged", attendee_id=attendee_id,
                                source=_join(r.email_source for r in group),
                                note=f"{len(group)} emails from one person"))
    attendee = Attendee(attendee_id=attendee_id, company_number=absent(), **values, flags=sorted(flags),
                        source_keys=[r.email_key for r in group], candidates=candidates)
    return attendee, audit


def dedupe(records: list[Record]) -> tuple[list[Attendee], list[AuditEntry]]:
    """Exact email match first, then a fuzzy match on name and company. IDs follow the first email date."""
    groups: list[list[Record]] = []
    for record in sorted(records, key=lambda r: r.date):
        group = next((g for g in groups if _same_person(g, record)), None)
        if group is None:
            groups.append([record])
        else:
            group.append(record)
    attendees, audit = [], []
    for i, group in enumerate(groups, start=1):
        attendee, entries = _merge(f"A{i:02d}", group)
        attendees.append(attendee)
        audit += entries
    return attendees, audit


# Verification

def emails_of(attendee: Attendee) -> set[str]:
    values = [attendee.email.value] + [fv.value for fv in attendee.candidates.get("email", [])]
    return {v.lower() for v in values if v}


def crm_match(attendee: Attendee, crm: list[CrmContact]) -> CrmContact | None:
    emails = emails_of(attendee)
    for contact in crm:
        if contact.email.lower() in emails:
            return contact
    name, company = attendee.full_name.value, attendee.company.value
    if name and company:
        for contact in crm:
            if fuzz.token_sort_ratio(name_key(name), name_key(contact.full_name)) >= CRM_NAME_MIN \
                    and fuzz.token_sort_ratio(company_key(company), company_key(contact.company or "")) >= COMPANY_MIN:
                return contact
    return None


def _settle_conflicts(a: Attendee, contact: CrmContact, flags: set[str], audit: list[AuditEntry]) -> None:
    """A conflict that the CRM settles is a rule, so code settles it; the agent gets only judgement calls."""
    for field, options in list(a.candidates.items()):
        crm_value = getattr(contact, field, None)
        matches = [o for o in options if crm_value and value_key(field, o.value) == value_key(field, crm_value)]
        if len(matches) != 1:
            continue
        chosen = matches[0]
        others = "; ".join(f"{o.value} ({o.source})" for o in options if o is not chosen)
        setattr(a, field, FieldValue(value=chosen.value, status="verified", source=_join([contact.source, chosen.source]),
                                     note=f"the CRM confirms this value; other value: {others}"))
        flags.discard(f"{field}_conflict")
        del a.candidates[field]
        audit.append(AuditEntry(step="verify", action="rule", attendee_id=a.attendee_id, field=field,
                                after=chosen.value, source=contact.source, note=f"the CRM settles the conflict; other: {others}"))


def _compare(a: Attendee, field: str, crm_value: str | None, flag: str, contact: CrmContact,
             flags: set[str], audit: list[AuditEntry]) -> None:
    fv = a.field(field)
    if fv.value is None or crm_value is None or fv.status == "conflict":
        return
    if value_key(field, fv.value) != value_key(field, crm_value):
        setattr(a, field, fv.model_copy(update={"status": "conflict", "note": f"the CRM has {crm_value!r} ({contact.source})"}))
        flags.add(flag)
        audit.append(AuditEntry(step="verify", action="flagged", attendee_id=a.attendee_id, field=field,
                                before=fv.value, source=contact.source, note=f"{flag}: the CRM has {crm_value!r}"))
    elif field == "company" and fv.value != crm_value:
        # Same firm, fuller form in the CRM (for example with its suffix).
        setattr(a, field, FieldValue(value=crm_value, status="corrected", source=_join([fv.source, contact.source]),
                                     note=f"was {fv.value!r}"))
        audit.append(AuditEntry(step="verify", action="changed", attendee_id=a.attendee_id, field=field,
                                before=fv.value, after=crm_value, source=contact.source))
    else:
        setattr(a, field, fv.model_copy(update={"source": _join([fv.source, contact.source])}))


def _check_phone(a: Attendee, contact: CrmContact, flags: set[str], audit: list[AuditEntry]) -> None:
    fv = a.phone
    if not contact.phone:
        return
    if fv.value is None:
        a.phone = FieldValue(value=contact.phone, status="corrected", source=contact.source,
                             note="absent in the email; filled from the CRM")
        audit.append(AuditEntry(step="verify", action="filled", attendee_id=a.attendee_id, field="phone",
                                after=contact.phone, source=contact.source))
    elif fv.status == "conflict":
        a.phone = fv.model_copy(update={"note": f"{fv.note}; the CRM has {contact.phone} ({contact.source})"})
    elif fv.value != contact.phone:
        a.phone = fv.model_copy(update={"status": "conflict", "note": f"the CRM has {contact.phone} ({contact.source})"})
        flags.add("phone_differs_from_crm")
        audit.append(AuditEntry(step="verify", action="flagged", attendee_id=a.attendee_id, field="phone",
                                before=fv.value, source=contact.source, note="phone_differs_from_crm"))
    else:
        a.phone = fv.model_copy(update={"source": _join([fv.source, contact.source])})


def _check_company_register(a: Attendee, companies: CompanyCheck | None, flags: set[str],
                            audit: list[AuditEntry]) -> None:
    if not a.company.value or companies is None:
        return
    try:
        result = companies(a.company.value)
    except ToolError as err:
        a.company_number = absent(note=f"web check failed: {err}")
        flags.add("web_check_failed")
        audit.append(AuditEntry(step="verify", action="flagged", attendee_id=a.attendee_id, field="company_number",
                                note=f"web_check_failed: {err}"))
        return
    if not result.found:
        a.company_number = absent(note="not on the register (Companies House)")
        audit.append(AuditEntry(step="verify", action="note", attendee_id=a.attendee_id, field="company_number",
                                note=f"{a.company.value!r} is not on the register"))
        return
    a.company_number = FieldValue(value=result.number, status="verified", source=f"companies_house:{result.number}",
                                  note=f"registry name {result.name!r}; status {result.status}")
    if result.status and result.status != "active":
        flags.add("company_not_active")
        audit.append(AuditEntry(step="verify", action="flagged", attendee_id=a.attendee_id, field="company_number",
                                note=f"company_not_active: {result.status}"))


def verify_one(attendee: Attendee, *, crm: list[CrmContact], invited: set[str],
               companies: CompanyCheck | None) -> tuple[Attendee, list[AuditEntry]]:
    a = attendee.model_copy(deep=True)
    flags, audit = set(a.flags), []
    contact = crm_match(a, crm)
    if contact is None:
        audit.append(AuditEntry(step="verify", action="note", attendee_id=a.attendee_id, note="not in the CRM"))
    else:
        a.crm_id = contact.contact_id
        _settle_conflicts(a, contact, flags, audit)
        _compare(a, "full_name", contact.full_name, "name_differs_from_crm", contact, flags, audit)
        _compare(a, "company", contact.company, "company_differs_from_crm", contact, flags, audit)
        _compare(a, "email", contact.email, "email_differs_from_crm", contact, flags, audit)
        _check_phone(a, contact, flags, audit)
        if a.job_title.value is None and contact.job_title:
            a.job_title = FieldValue(value=contact.job_title, status="corrected", source=contact.source,
                                     note="absent in the email; filled from the CRM")
            audit.append(AuditEntry(step="verify", action="filled", attendee_id=a.attendee_id, field="job_title",
                                    after=contact.job_title, source=contact.source))
    for field in REQUIRED:
        if a.field(field).value is None:
            flags.add(f"{field}_absent")
    if a.phone.value is None:
        flags.add("phone_absent")
    if a.email.value and not _EMAIL.match(a.email.value):
        flags.add("email_invalid")
    if not emails_of(a) & invited:
        flags.add("not_invited")
        audit.append(AuditEntry(step="verify", action="flagged", attendee_id=a.attendee_id,
                                note="not_invited: no email of this record is on the invitee list"))
    if a.attending.value is None:
        flags.add("attendance_unclear")
    _check_company_register(a, companies, flags, audit)
    a.flags = sorted(flags)
    return a, audit


def verify(attendees: list[Attendee], *, crm: list[CrmContact], event: Event,
           companies: CompanyCheck | None) -> tuple[list[Attendee], list[AuditEntry]]:
    invited = {i.email.lower() for i in event.invitees}
    out, audit = [], []
    for attendee in attendees:
        checked, entries = verify_one(attendee, crm=crm, invited=invited, companies=companies)
        out.append(checked)
        audit += entries
    return out, audit


# Run level

def needs_review(attendee: Attendee) -> bool:
    return any(f not in INFO_FLAGS for f in attendee.flags)


def capacity_check(attendees: list[Attendee], seated_capacity: int | None) -> dict:
    attending = sum(1 for a in attendees if a.attending.value == "yes")
    return {"attending": attending, "seated_capacity": seated_capacity,
            "over_capacity": seated_capacity is not None and attending > seated_capacity}


def no_reply(event: Event, attendees: list[Attendee]) -> list[str]:
    replied = set().union(*(emails_of(a) for a in attendees)) if attendees else set()
    return [i.email for i in event.invitees if i.email.lower() not in replied]


def check_all(extractions: list[tuple[Email, ExtractedRsvp]], *, event: Event, crm: list[CrmContact],
              companies: CompanyCheck | None, seated_capacity: int | None) -> tuple[list[Attendee], list[AuditEntry], dict]:
    """All the code steps after extraction, in order. One call for a test or a single flow component."""
    records, audit = [], []
    for email, extracted in extractions:
        record, entries = ground(extracted, email)
        audit += entries
        record, entries = normalize(record)
        audit += entries
        records.append(record)
    attendees, entries = dedupe(records)
    audit += entries
    attendees, entries = verify(attendees, crm=crm, event=event, companies=companies)
    audit += entries
    report = {
        "emails": len(extractions),
        "attendees": len(attendees),
        "merged_emails": len(extractions) - len(attendees),
        "for_review": [a.attendee_id for a in attendees if needs_review(a)],
        "no_reply": no_reply(event, attendees),
        "capacity": capacity_check(attendees, seated_capacity),
    }
    return attendees, audit, report
