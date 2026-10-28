"""The agent's lookup tools and the flow conversions."""

import math
from types import SimpleNamespace

import pandas as pd

from eventai.agent import flow_io
from eventai.agent.flow_io import records
from eventai.agent.lookups import company_search, crm_lookup, invitee_lookup
from eventai.agent.tools import ToolError
from eventai.agent.tools.seed_files import load_crm, load_event


def test_crm_lookup_by_email_name_or_company():
    crm = load_crm()
    assert [r["contact_id"] for r in crm_lookup("SAM.OKORO@saltmere.example", crm)] == ["C007"]
    assert [r["contact_id"] for r in crm_lookup("Sam Okoro", crm)] == ["C007"]
    assert {r["contact_id"] for r in crm_lookup("Tallowmere Foods", crm)} == {"C001", "C004", "C009", "C012"}
    assert crm_lookup("sam.okoru@saltmere.example", crm) == []  # a typo finds nothing: the agent tries again
    assert crm_lookup("C007", crm) == []
    row = crm_lookup("Robert Harper", crm)[0]
    assert row["phone"] == "+441134960388" and row["source"] == "crm.csv#C006"


def test_invitee_lookup():
    event = load_event()
    assert invitee_lookup("Tom Price", event) == [
        {"email": "tom.price@tallowmere.example", "name": "Tom Price", "source": "calendar:invitees"}]
    assert invitee_lookup("leah.morgan@tallowmere.example", event) == []


def test_company_search_turns_a_failure_into_a_result():
    def broken(name):
        raise ToolError("no Companies House API key")

    assert company_search("Acme", broken) == {"error": "no Companies House API key"}
    not_found = SimpleNamespace(found=False, number=None, name=None, status=None)
    assert company_search("Acme", lambda n: not_found)["source"] == "companies_house:search"


def test_records_from_each_flow_type():
    frame = pd.DataFrame([{"a": 1, "b": None}, {"a": 2, "b": "x"}])
    frame.loc[0, "b"] = math.nan
    assert records(frame) == [{"a": 1, "b": None}, {"a": 2, "b": "x"}]
    assert records([SimpleNamespace(data={"a": 1})]) == [{"a": 1}]
    assert records(SimpleNamespace(data={"results": [{"a": 1}, {"a": 2}]})) == [{"a": 1}, {"a": 2}]
    assert records(SimpleNamespace(data={"a": 1})) == [{"a": 1}]
    assert records(None) == []


def test_a_table_round_trip_keeps_is_rsvp_a_bool():
    from eventai.agent.schema import ExtractedRsvp

    rows = [ExtractedRsvp(is_rsvp=flag, full_name="Jo", email=None, phone=None, company=None, job_title=None,
                          dietary_needs=None, attending=None).model_dump() for flag in (False, True)]
    back = [ExtractedRsvp.model_validate(r) for r in records(pd.DataFrame(rows))]
    assert [r.is_rsvp for r in back] == [False, True]


def test_the_tool_reads_the_event_that_load_event_remembered(monkeypatch):
    monkeypatch.setattr(flow_io, "_event", None)
    assert flow_io.remembered_event().event_id == "partnersummit2026"  # no run yet: the seed event
    other = load_event().model_copy(update={"event_id": "other", "invitees": []})
    flow_io.remember_event(other)
    assert flow_io.remembered_event() is other
