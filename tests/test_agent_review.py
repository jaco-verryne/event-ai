"""The agent step around the LLM: the review queue and the code check of decisions (D12)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eventai.agent import checks
from eventai.agent.output import read_rows, write_outputs
from eventai.agent.review import Decision, apply_decisions, flag_field, review_items
from eventai.agent.schema import ExtractedRsvp
from eventai.agent.tools.seed_files import SEED_DIR, load_crm, load_emails, load_event

NOT_FOUND = SimpleNamespace(found=False, number=None, name=None, status=None)
spec = importlib.util.spec_from_file_location("run_part2", SEED_DIR.parent / "eval" / "run_part2.py")
run_part2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_part2)


@pytest.fixture(scope="module")
def seed():
    canned = yaml.safe_load((Path(__file__).parent / "fixtures" / "part2_extractions.yaml").read_text())
    emails, event, crm = load_emails(), load_event(), load_crm()
    pairs = [(e, ExtractedRsvp(**canned[e.key])) for e in emails]
    attendees, audit, report = checks.check_all(pairs, event=event, crm=crm, companies=lambda n: NOT_FOUND,
                                                seated_capacity=100)
    by_key = {";".join(a.source_keys): a for a in attendees}
    return SimpleNamespace(attendees=attendees, audit=audit, report=report, emails=emails, event=event, crm=crm,
                           by_key=by_key)


def apply(seed, decisions):
    return apply_decisions(seed.attendees, decisions, emails=seed.emails, crm=seed.crm, event=seed.event)


@pytest.mark.parametrize("flag, field", [
    ("name_differs_from_crm", "full_name"), ("phone_invalid", "phone"), ("email_conflict", "email"),
    ("company_absent", "company"), ("not_in_source:job_title", "job_title"), ("attendance_unclear", "attending"),
    ("not_invited", None),
])
def test_flag_field(flag, field):
    assert flag_field(flag) == field


def test_review_queue_has_one_item_for_each_review_flag(seed):
    items = review_items(seed.attendees, seed.emails)
    assert sorted((i["attendee_id"], i["flag"]) for i in items) == [
        ("A05", "name_differs_from_crm"), ("A06", "phone_invalid"), ("A07", "company_differs_from_crm"),
        ("A09", "not_invited"), ("A10", "attendance_unclear")]
    phone = next(i for i in items if i["flag"] == "phone_invalid")
    assert "the CRM has +441134960712 (crm.csv#C007)" in phone["text"]
    assert "My mobile is 0113 496 07" in phone["text"]


def test_a_value_from_the_crm_is_applied(seed):
    a06 = seed.by_key["e10"].attendee_id
    out, audit = apply(seed, [Decision(attendee_id=a06, flag="phone_invalid", action="use_value",
                                       value="0113 496 0712", source="crm.csv#C007", reason="The CRM has a full number.")])
    fixed = next(a for a in out if a.attendee_id == a06)
    assert fixed.phone.value == "+441134960712"
    assert fixed.phone.status == "corrected"
    assert fixed.phone.source == "crm.csv#C007"
    assert fixed.resolutions == ["phone_invalid:use_value"]
    assert next(e for e in audit if e.attendee_id == a06).before == "0113 496 07"


def test_an_invented_value_goes_to_human_review(seed):
    a05 = seed.by_key["e07"].attendee_id
    out, audit = apply(seed, [Decision(attendee_id=a05, flag="name_differs_from_crm", action="use_value",
                                       value="Roberto Harpo", reason="guess")])
    record = next(a for a in out if a.attendee_id == a05)
    assert record.full_name.value == "Bob Harper"
    assert record.resolutions == ["name_differs_from_crm:human_review"]
    assert "value not in evidence" in next(e for e in audit if e.attendee_id == a05).note


def test_unknown_and_missing_decisions_go_to_human_review(seed):
    a05 = seed.by_key["e07"].attendee_id
    out, audit = apply(seed, [Decision(attendee_id=a05, flag="name_differs_from_crm", action="correct")])
    notes = {e.attendee_id: e.note for e in audit}
    assert "unknown action 'correct'" in notes[a05]
    assert notes[seed.by_key["e12"].attendee_id] == "no decision from the agent"
    assert all(r.endswith(":human_review") for a in out for r in a.resolutions)


def test_keep_is_recorded(seed):
    a10 = seed.by_key["e12"].attendee_id
    out, _ = apply(seed, [Decision(attendee_id=a10, flag="attendance_unclear", action="keep", reason="x")])
    assert next(a for a in out if a.attendee_id == a10).resolutions == ["attendance_unclear:keep"]


def test_the_expected_decisions_score_full_marks(seed, tmp_path):
    ids = {k: a.attendee_id for k, a in seed.by_key.items()}
    decisions = [
        Decision(attendee_id=ids["e07"], flag="name_differs_from_crm", action="use_value", value="Robert Harper",
                 source="crm.csv#C006"),
        Decision(attendee_id=ids["e10"], flag="phone_invalid", action="use_value", value="+441134960712",
                 source="crm.csv#C007"),
        Decision(attendee_id=ids["e08"], flag="company_differs_from_crm", action="use_value",
                 value="Brightwyn Analytics Ltd", source="crm.csv#C008"),
        Decision(attendee_id=ids["e11"], flag="not_invited", action="human_review", reason="a substitute"),
        Decision(attendee_id=ids["e12"], flag="attendance_unclear", action="human_review", reason="maybe"),
    ]
    attendees, audit = apply(seed, decisions)
    paths = write_outputs(tmp_path, attendees, seed.audit + audit, seed.report)
    scores = run_part2.score(read_rows(SEED_DIR / "expected_attendees.csv"), read_rows(paths["attendees"]))
    assert scores["flags"]["precision"] == scores["flags"]["recall"] == 1.0
    assert scores["fields"]["accuracy"] == 1.0
    assert scores["resolutions"]["accuracy"] == 1.0
