"""RSVP extraction around any model (eventai/agent/extract.py)."""

import json

import pytest

from eventai.agent.extract import ExtractionFailed, extract_rsvp, messages_for, parse
from eventai.agent.tools.seed_files import load_emails

GOOD = json.dumps({"full_name": "Sam Okoro", "email": "sam.okoro@saltmere.example", "phone": "0113 496 07",
                   "company": "Saltmere Freight PLC", "job_title": "Operations Manager", "dietary_needs": None,
                   "attending": True})


@pytest.fixture(scope="module")
def email():
    return next(e for e in load_emails() if e.key == "e10")


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_messages_hold_the_rules_the_schema_and_the_email(email):
    system, user = messages_for(email)
    assert "Do not infer a value" in system["content"]
    assert '"attending"' in system["content"]
    assert user["content"] == email.text


def test_the_prompt_asks_whether_the_email_is_an_rsvp(email):
    system, _ = messages_for(email)
    assert "is_rsvp" in system["content"] and "out of office" in system["content"]
    assert "a substitute is an RSVP" in system["content"]  # e11 must stay on the list


def test_is_rsvp_reads_false_and_defaults_to_true():
    assert parse(json.dumps({**json.loads(GOOD), "is_rsvp": False})).is_rsvp is False
    assert parse(GOOD).is_rsvp is True  # a reply without the field keeps the email


def test_parse_accepts_a_code_fence():
    assert parse(f"```json\n{GOOD}\n```").full_name == "Sam Okoro"


def test_one_call_when_the_output_is_valid(email):
    model = Scripted(GOOD)
    assert extract_rsvp(email, model).phone == "0113 496 07"
    assert len(model.calls) == 1


def test_one_retry_with_the_error(email):
    model = Scripted('{"full_name": "Sam Okoro"}', GOOD)
    assert extract_rsvp(email, model).company == "Saltmere Freight PLC"
    assert "Your JSON is not valid" in model.calls[1][-1]["content"]


def test_two_invalid_outputs_fail(email):
    with pytest.raises(ExtractionFailed, match="e10"):
        extract_rsvp(email, Scripted("not json", "still not json"))
