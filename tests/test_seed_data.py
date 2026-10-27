"""The Part 2 seed files agree with each other and hold only synthetic data (CLAUDE.md 10.7, D13)."""

import csv
import re

import phonenumbers
import pytest

from eventai.agent.tools.seed_files import (
    SEED_DIR, load_crm, load_emails, load_event, venue_capacity, venue_id_from,
)

KNOWN_FLAGS = {
    "name_differs_from_crm", "company_differs_from_crm", "phone_absent", "phone_invalid",
    "not_invited", "attendance_unclear",
}
# Ofcom drama ranges: Leeds 0113 496 0xxx, Manchester 0161 496 0xxx, London 020 7946 0xxx.
# Up to 3 final digits, because one seed number is short on purpose (e10).
DRAMA = re.compile(r"^0(?:1134960|1614960|2079460)\d{0,3}$")


def national_digits(phone):
    digits = re.sub(r"\D", "", phone)
    return "0" + digits[2:] if digits.startswith("44") else digits


@pytest.fixture(scope="module")
def event():
    return load_event()


@pytest.fixture(scope="module")
def emails():
    return load_emails()


@pytest.fixture(scope="module")
def expected():
    with (SEED_DIR / "expected_attendees.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def test_event(event):
    assert event.event_id == "partnersummit2026"
    assert event.venue_id == "V113"
    assert venue_capacity(event.venue_id) == 100
    assert len(event.invitees) == 12
    assert len({i.email for i in event.invitees}) == 12


def test_venue_id_from_description():
    assert venue_id_from("Talks and drinks.\nVenue: V012 (The Old Mill)") == "V012"
    assert venue_id_from("No venue yet.") is None


def test_emails_have_unique_keys_in_the_message_id(emails):
    assert [e.key for e in emails] == [f"e{i:02d}" for i in range(1, 14)]
    assert all(e.rfc_message_id == f"<{e.key}.partnersummit2026@seed.example>" for e in emails)
    assert all(e.source == f"seed:{e.key}" for e in emails)


def test_email_text_holds_the_headers(emails):
    text = emails[0].text
    assert text.startswith("From: Amelia Hart <amelia.hart@tallowmere.example>")
    assert "Subject: Re: Invitation: Northern Partners Summit 2026" in text


def test_only_example_domains(event, emails):
    addresses = [i.email for i in event.invitees] + [e.sender_email for e in emails]
    addresses += [c.email for c in load_crm()]
    assert all(a.lower().endswith(".example") for a in addresses)


def test_only_drama_range_phone_numbers(emails):
    phones = [c.phone for c in load_crm()]
    for e in emails:
        phones += re.findall(r"0\d{2,3} \d{3,4} ?\d{0,4}", e.body)
    assert phones
    for phone in phones:
        assert DRAMA.match(national_digits(phone)), phone


def test_crm_ids_are_unique_and_phones_valid():
    crm = load_crm()
    assert len({c.contact_id for c in crm}) == len(crm)
    for c in crm:
        assert phonenumbers.is_valid_number(phonenumbers.parse(c.phone, "GB")), c.contact_id


def test_expected_rows_cover_each_email_once(emails, expected):
    keys = [k for row in expected for k in row["source_keys"].split(";")]
    assert sorted(keys) == sorted(e.key for e in emails)


def test_expected_flags_and_resolutions(expected):
    flags = [f for row in expected for f in row["flags"].split(";") if f]
    assert set(flags) <= KNOWN_FLAGS
    assert len(flags) == 6
    for row in expected:
        for resolution in filter(None, row["resolution"].split(";")):
            flag, action = resolution.split(":")
            assert flag in row["flags"].split(";")
            assert action in {"use_value", "keep", "human_review"}
