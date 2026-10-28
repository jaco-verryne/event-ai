"""Part 2 code checks: one test per rule, then the full seed set against the expected output."""

import csv
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import yaml

from eventai.agent import checks
from eventai.agent.schema import CrmContact, Email, Event, ExtractedRsvp, FieldValue, Invitee, Record, absent
from eventai.agent.tools import ToolError
from eventai.agent.tools.seed_files import SEED_DIR, load_crm, load_emails, load_event

FIXTURES = SEED_DIR.parent / "tests" / "fixtures"
NOT_FOUND = SimpleNamespace(found=False, number=None, name=None, status=None)


def email(key="e01", body="Hi,\nYes I will attend.\n\nJo Bloggs\nAcme Ltd\n0113 496 0101", sender="jo@acme.example",
          name="Jo Bloggs", day=2):
    return Email(message_id=key, rfc_message_id=f"<{key}.x@seed.example>", source=f"seed:{key}", sender_name=name,
                 sender_email=sender, date=datetime(2026, 11, day, 9, tzinfo=timezone.utc), subject="RSVP", body=body)


def extracted(**overrides):
    values = dict(full_name="Jo Bloggs", email="jo@acme.example", phone="0113 496 0101", company="Acme Ltd",
                  job_title=None, dietary_needs=None, attending=True)
    return ExtractedRsvp(**{**values, **overrides})


def record(key="e01", day=2, **values):
    fields = {f: absent() for f in ("full_name", "email", "phone", "company", "job_title", "dietary_needs", "attending")}
    for field, value in values.items():
        fields[field] = FieldValue(value=value, status="verified", source=f"seed:{key}")
    return Record(email_key=key, email_source=f"seed:{key}", date=datetime(2026, 11, day, tzinfo=timezone.utc),
                  fields=fields)


# Grounding

def test_grounding_keeps_values_found_in_the_email():
    rec, audit = checks.ground(extracted(), email())
    assert rec.fields["full_name"].value == "Jo Bloggs"
    assert rec.fields["email"].source == "seed:e01"
    assert rec.fields["attending"].value == "yes"
    assert rec.flags == [] and audit == []


def test_grounding_removes_an_invented_value():
    rec, audit = checks.ground(extracted(company="Acme Holdings Group", job_title="CEO"), email())
    assert rec.fields["company"].value is None
    assert rec.fields["company"].status == "absent"
    assert "not_in_source:company" in rec.flags
    assert {a.field for a in audit} == {"company", "job_title"}


def test_grounding_matches_a_phone_by_its_digits():
    assert checks.grounded("phone", "+44 113 496 0101", "call 0113 496 0101")
    assert not checks.grounded("phone", "0113 496 0199", "call 0113 496 0101")


def test_grounding_reads_the_email_address_in_the_headers():
    assert checks.grounded("email", "JO@ACME.EXAMPLE", email(body="Yes.").text)


def test_attending_null_stays_absent():
    rec, _ = checks.ground(extracted(attending=None), email())
    assert rec.fields["attending"].status == "absent"


# Normalization

@pytest.mark.parametrize("raw, expected", [
    ("priya shah", "Priya Shah"), ("JOHN SMITH", "John Smith"), ("o'neil", "O'Neil"),
    ("mary-jane mcdonald", "Mary-Jane McDonald"), ("Leah  Morgan", "Leah Morgan"), ("DeShawn McKay", "DeShawn McKay"),
])
def test_normalize_name(raw, expected):
    assert checks.normalize_name(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Acme limited", "Acme Ltd"), ("Acme LTD.", "Acme Ltd"), ("Saltmere Freight plc", "Saltmere Freight PLC"),
    ("Quillmere Events", "Quillmere Events"),
])
def test_normalize_company(raw, expected):
    assert checks.normalize_company(raw) == expected


def test_company_key_ignores_case_punctuation_and_suffix():
    assert checks.company_key("Quillmere Events Ltd") == checks.company_key("quillmere events")
    assert checks.company_key("Smith & Co. Limited") == "smith and co"
    # The register writes some suffixes with dots (found in the live check on 27 Oct).
    assert checks.company_key("MARKS AND SPENCER GROUP P.L.C.") == checks.company_key("Marks and Spencer Group PLC")


def test_normalize_phone():
    assert checks.normalize_phone("0113 496 0461") == ("+441134960461", True)
    assert checks.normalize_phone("0113 496 07") == ("0113 496 07", False)
    assert checks.normalize_phone("not a number") == ("not a number", False)


def test_normalize_records_each_change():
    rec = record(full_name="priya shah", email="Priya.Shah@Vellanthe.example", phone="0161 496 0202",
                 dietary_needs="vegetarian,")
    out, audit = checks.normalize(rec)
    assert out.fields["full_name"].value == "Priya Shah"
    assert out.fields["email"].value == "priya.shah@vellanthe.example"
    assert out.fields["phone"].value == "+441614960202"
    assert out.fields["dietary_needs"].value == "vegetarian"
    assert out.fields["phone"].status == "corrected" and out.fields["phone"].note == "was '0161 496 0202'"
    assert len(audit) == 4


def test_an_invalid_phone_keeps_its_value_and_gets_a_flag():
    out, audit = checks.normalize(record(phone="0113 496 07"))
    assert out.fields["phone"].value == "0113 496 07"
    assert out.fields["phone"].status == "conflict"
    assert out.flags == ["phone_invalid"]
    assert audit[0].action == "flagged"


# Deduplication

def test_exact_email_duplicates_merge_and_the_later_dietary_need_wins():
    first = record("e03", 2, full_name="Marcus Bell", email="m@t.example", company="Thistlewick Hotels Ltd",
                   attending="yes")
    second = record("e04", 3, full_name="Marcus Bell", email="m@t.example", dietary_needs="vegetarian")
    attendees, audit = checks.dedupe([second, first])
    assert len(attendees) == 1
    a = attendees[0]
    assert a.source_keys == ["e03", "e04"]
    assert a.dietary_needs.value == "vegetarian"
    assert a.attending.value == "yes"
    assert a.full_name.source == "seed:e03 + seed:e04"
    assert audit[-1].action == "merged"


def test_fuzzy_duplicates_merge_with_conflicts():
    work = record("e05", 3, full_name="Jonathon Reed", email="j.reed@q.example", company="Quillmere Events Ltd")
    home = record("e06", 5, full_name="Jonathan Reed", email="jon@mailbox.example", company="Quillmere Events")
    attendees, _ = checks.dedupe([work, home])
    assert len(attendees) == 1
    a = attendees[0]
    assert a.company.value == "Quillmere Events Ltd"  # one firm; the fuller form wins
    assert {"full_name_conflict", "email_conflict"} <= set(a.flags)
    assert [c.value for c in a.candidates["email"]] == ["j.reed@q.example", "jon@mailbox.example"]


def test_different_people_stay_apart():
    a = record("e01", 2, full_name="Sam Okoro", email="sam@s.example", company="Saltmere Freight PLC")
    b = record("e02", 3, full_name="Sam Price", email="sp@t.example", company="Tallowmere Foods Ltd")
    attendees, _ = checks.dedupe([a, b])
    assert [x.attendee_id for x in attendees] == ["A01", "A02"]


# Verification

CRM = [CrmContact(contact_id="C005", full_name="Jonathan Reed", email="j.reed@q.example", phone="+441134960461",
                  company="Quillmere Events Ltd", job_title="Head of Partnerships")]
EVENT = Event(event_id="x", summary="Summit", start=datetime(2026, 11, 26, tzinfo=timezone.utc),
              invitees=[Invitee(email="j.reed@q.example")])


def verified(attendee, companies=lambda name: NOT_FOUND):
    out, audit = checks.verify([attendee], crm=CRM, event=EVENT, companies=companies)
    return out[0], audit


def one(**values):
    attendees, _ = checks.dedupe([record(**values)])
    return attendees[0]


def test_the_crm_settles_a_conflict_by_rule():
    work = record("e05", 3, full_name="Jonathon Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                  attending="yes")
    home = record("e06", 5, full_name="Jonathan Reed", email="jon@mailbox.example", company="Quillmere Events")
    a, audit = verified(checks.dedupe([work, home])[0][0])
    assert a.full_name.value == "Jonathan Reed"
    assert a.full_name.status == "verified"
    assert a.full_name.source == "crm.csv#C005 + seed:e06"
    assert a.email.value == "j.reed@q.example"
    assert "full_name_conflict" not in a.flags and "email_conflict" not in a.flags
    assert a.crm_id == "C005"
    assert [e.field for e in audit if e.action == "rule"] == ["full_name", "email"]


def test_a_name_that_differs_from_the_crm_is_flagged():
    a, _ = verified(one(full_name="Jon Reed", email="j.reed@q.example", company="Quillmere Events Ltd", attending="yes"))
    assert "name_differs_from_crm" in a.flags
    assert a.full_name.status == "conflict"
    assert a.full_name.note == "the CRM has 'Jonathan Reed' (crm.csv#C005)"


def test_a_firm_that_differs_from_the_crm_is_flagged():
    a, _ = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Evnts",
                        attending="yes"))
    assert "company_differs_from_crm" in a.flags


def test_the_crm_adds_the_company_suffix():
    a, _ = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events",
                        attending="yes"))
    assert a.company.value == "Quillmere Events Ltd"
    assert a.company.status == "corrected"
    assert "company_differs_from_crm" not in a.flags


def test_an_absent_phone_comes_from_the_crm():
    a, audit = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                            attending="yes"))
    assert a.phone.value == "+441134960461"
    assert a.phone.source == "crm.csv#C005"
    assert "phone_absent" not in a.flags
    assert any(e.action == "filled" and e.field == "phone" for e in audit)


def test_an_invalid_phone_keeps_its_flag_for_the_agent():
    rec, _ = checks.normalize(record(full_name="Jonathan Reed", email="j.reed@q.example", phone="0113 496 07",
                                     company="Quillmere Events Ltd", attending="yes"))
    a, _ = verified(checks.dedupe([rec])[0][0])
    assert "phone_invalid" in a.flags
    assert "the CRM has +441134960461" in a.phone.note
    assert checks.needs_review(a)


def test_not_in_crm_not_invited_unclear_and_no_phone():
    a, audit = verified(one(full_name="Leah Morgan", email="leah@t.example", company="Tallowmere Foods Ltd"))
    assert {"not_invited", "attendance_unclear", "phone_absent"} <= set(a.flags)
    assert a.crm_id is None
    assert any(e.note == "not in the CRM" for e in audit)


def test_required_fields_absent():
    a, _ = verified(one(email="nobody@x.example", attending="yes"))
    assert {"full_name_absent", "company_absent"} <= set(a.flags)


def test_phone_absent_alone_is_info_only():
    a = one(full_name="Oliver Grant", email="j.reed@q.example", company="Quillmere Events Ltd", attending="yes")
    a = a.model_copy(update={"flags": ["phone_absent", "web_check_failed"]})
    assert not checks.needs_review(a)


def test_register_not_found_is_a_note_not_a_flag():
    a, audit = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                            attending="yes"))
    assert a.company_number.status == "absent"
    assert a.company_number.note == "not on the register (Companies House)"
    assert a.flags == []


def test_register_found_gives_the_company_number():
    found = SimpleNamespace(found=True, number="01234567", name="QUILLMERE EVENTS LIMITED", status="active")
    a, _ = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                        attending="yes"), companies=lambda name: found)
    assert a.company_number.value == "01234567"
    assert a.company_number.source == "companies_house:01234567"
    assert a.flags == []


def test_a_dissolved_company_is_flagged():
    found = SimpleNamespace(found=True, number="01234567", name="QUILLMERE EVENTS LIMITED", status="dissolved")
    a, _ = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                        attending="yes"), companies=lambda name: found)
    assert "company_not_active" in a.flags


def test_a_failed_web_check_flags_the_record_and_the_run_goes_on():
    def broken(name):
        raise ToolError("timeout after 3 tries")

    a, _ = verified(one(full_name="Jonathan Reed", email="j.reed@q.example", company="Quillmere Events Ltd",
                        attending="yes"), companies=broken)
    assert a.flags == ["web_check_failed"]
    assert a.company_number.note == "web check failed: timeout after 3 tries"
    assert not checks.needs_review(a)


def test_capacity_check():
    a = one(full_name="Jo", email="j@x.example", company="X Ltd", attending="yes")
    assert checks.capacity_check([a, a], 1) == {"attending": 2, "seated_capacity": 1, "over_capacity": True}
    assert checks.capacity_check([a], None)["over_capacity"] is False


# The full seed set

@pytest.fixture(scope="module")
def seed_run():
    canned = yaml.safe_load((FIXTURES / "part2_extractions.yaml").read_text())
    emails = load_emails()
    pairs = [(e, ExtractedRsvp(**canned[e.key])) for e in emails]
    return checks.check_all(pairs, event=load_event(), crm=load_crm(), companies=lambda name: NOT_FOUND,
                            seated_capacity=100)


@pytest.fixture(scope="module")
def expected():
    with (SEED_DIR / "expected_attendees.csv").open(newline="") as f:
        return {row["source_keys"]: row for row in csv.DictReader(f)}


def test_seed_run_gives_the_expected_records_and_flags(seed_run, expected):
    attendees, _, _ = seed_run
    assert {";".join(a.source_keys) for a in attendees} == set(expected)
    for a in attendees:
        row = expected[";".join(a.source_keys)]
        assert a.flags == sorted(filter(None, row["flags"].split(";"))), a.attendee_id


def test_seed_run_values_before_the_agent_step(seed_run, expected):
    # The agent step changes the fields of the use_value resolutions; until then the email value stays.
    before_agent = {"e07": {"full_name": "Bob Harper"}, "e08": {"company": "Brightwyn Analytcs"},
                    "e10": {"phone": "0113 496 07"}}
    attendees, _, _ = seed_run
    for a in attendees:
        key = ";".join(a.source_keys)
        row = expected[key]
        for field in ("full_name", "email", "phone", "company", "job_title", "dietary_needs", "attending"):
            want = before_agent.get(key, {}).get(field, row[field] or None)
            assert a.field(field).value == want, (key, field)


def test_seed_run_report(seed_run):
    attendees, audit, report = seed_run
    assert report["emails"] == 13
    assert report["attendees"] == 11
    assert report["merged_emails"] == 2
    assert report["no_reply"] == ["tom.price@tallowmere.example", "ravi.desai@brackenlow.example"]
    assert report["capacity"] == {"attending": 9, "seated_capacity": 100, "over_capacity": False}
    by_key = {";".join(a.source_keys): a.attendee_id for a in attendees}
    # IDs follow the date of the first email, so e10 (4 Nov 08:05) comes before e08.
    assert sorted(by_key[k] for k in ("e07", "e08", "e10", "e11", "e12")) == report["for_review"]
    assert by_key["e10"] == "A06"
    assert all(entry.step in {"ground", "normalize", "dedupe", "verify"} for entry in audit)
    assert report["not_rsvp"] == []


def test_emails_that_are_not_rsvps_stay_off_the_list_but_in_the_audit_and_the_report():
    canned = yaml.safe_load((FIXTURES / "part2_extractions.yaml").read_text())
    noise = [e for e in load_emails(SEED_DIR / "noise_emails.yaml") if e.key in canned]  # what the search finds
    pairs = [(e, ExtractedRsvp(**canned[e.key])) for e in load_emails() + noise]
    attendees, audit, report = checks.check_all(pairs, event=load_event(), crm=load_crm(),
                                                companies=lambda name: NOT_FOUND, seated_capacity=100)
    assert {k for a in attendees for k in a.source_keys} == {f"e{i:02d}" for i in range(1, 14)}
    assert (report["emails"], report["attendees"], report["merged_emails"]) == (13, 11, 2)
    assert report["not_rsvp"] == [
        {"email_key": "e15", "from": "ravi.desai@brackenlow.example",
         "subject": "Automatic reply: Invitation: Northern Partners Summit 2026"},
        {"email_key": "e16", "from": "hannah.wilde@fenwickrowe.example",
         "subject": "Catering quote: Northern Partners Summit, 26 November"},
    ]
    assert "ravi.desai@brackenlow.example" in report["no_reply"]  # an auto-reply is not a reply
    skipped = [e for e in audit if e.step == "filter"]
    assert [(e.action, e.email_key, e.source) for e in skipped] == [("skipped", "e15", "seed:e15"),
                                                                    ("skipped", "e16", "seed:e16")]
    assert skipped[0].note == "not an RSVP: Automatic reply: Invitation: Northern Partners Summit 2026"


@pytest.mark.parametrize("is_rsvp", [True, None])
def test_only_an_explicit_false_skips_an_email(is_rsvp):
    event = Event(event_id="x", summary="X", start=datetime(2026, 11, 26, tzinfo=timezone.utc),
                  invitees=[Invitee(email="jo@acme.example")])
    attendees, _, report = checks.check_all([(email(), extracted(is_rsvp=is_rsvp))], event=event, crm=[],
                                            companies=None, seated_capacity=None)
    assert len(attendees) == 1 and report["not_rsvp"] == []
