"""The Part 2 scorer (eval/run_part2.py) and the output files it reads."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eventai.agent import checks
from eventai.agent.output import ATTENDEE_COLUMNS, read_rows, write_outputs
from eventai.agent.schema import ExtractedRsvp
from eventai.agent.tools.seed_files import SEED_DIR, load_crm, load_emails, load_event

spec = importlib.util.spec_from_file_location(
    "run_part2", Path(__file__).resolve().parent.parent / "eval" / "run_part2.py"
)
run_part2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_part2)

NOT_FOUND = SimpleNamespace(found=False, number=None, name=None, status=None)


@pytest.fixture(scope="module")
def expected():
    return read_rows(SEED_DIR / "expected_attendees.csv")


def test_a_perfect_run_scores_full_marks(expected):
    report = run_part2.score(expected, copy.deepcopy(expected))
    assert report["flags"]["precision"] == report["flags"]["recall"] == 1.0
    assert report["fields"]["accuracy"] == 1.0
    assert report["deduplication"]["exact_groups"] == 11
    assert report["resolutions"]["accuracy"] == 1.0 and report["resolutions"]["total"] == 5


def test_the_late_rsvp_counts_only_when_the_run_read_it(expected):
    late = read_rows(SEED_DIR / "expected_late.csv")
    assert run_part2.with_late_rows(expected, late, copy.deepcopy(expected)) == expected
    after_demo = copy.deepcopy(expected) + copy.deepcopy(late)
    rows = run_part2.with_late_rows(expected, late, after_demo)
    assert [r["source_keys"] for r in rows][-1] == "e14"
    assert run_part2.score(rows, after_demo)["deduplication"]["exact_groups"] == 12


def test_flag_precision_and_recall(expected):
    output = copy.deepcopy(expected)
    by_key = {r["source_keys"]: r for r in output}
    by_key["e01"]["flags"] = "phone_invalid"          # extra
    by_key["e09"]["flags"] = ""                       # missed
    by_key["e02"]["flags"] = "web_check_failed"       # a tool failure: not scored
    flags = run_part2.score(expected, output)["flags"]
    assert (flags["true_positives"], flags["false_positives"], flags["false_negatives"]) == (5, 1, 1)
    assert flags["precision"] == flags["recall"] == round(5 / 6, 3)
    assert flags["tool_failure_flags"] == 1
    assert {m["source_keys"] for m in flags["misses"]} == {"e01", "e09"}


def test_a_wrong_merge_counts_against_the_merges_and_the_flags(expected):
    output = [r for r in copy.deepcopy(expected) if r["source_keys"] != "e05;e06"]
    output += [dict(expected[3], source_keys="e05", flags="name_differs_from_crm"),
               dict(expected[3], source_keys="e06", flags="")]
    report = run_part2.score(expected, output)
    assert report["deduplication"]["exact_groups"] == 10
    assert report["deduplication"]["wrong_groups"] == ["e05", "e06"]
    assert report["flags"]["false_positives"] == 1


def test_email_case_does_not_count_but_name_case_does(expected):
    output = copy.deepcopy(expected)
    output[1]["email"] = "Priya.Shah@Vellanthe.example"
    output[1]["full_name"] = "priya shah"
    fields = run_part2.score(expected, output)["fields"]
    assert [m["field"] for m in fields["misses"]] == ["full_name"]


def test_output_files_round_trip_and_score_before_the_agent_step(tmp_path, expected):
    canned = yaml.safe_load((Path(__file__).parent / "fixtures" / "part2_extractions.yaml").read_text())
    pairs = [(e, ExtractedRsvp(**canned[e.key])) for e in load_emails()]
    attendees, audit, report = checks.check_all(pairs, event=load_event(), crm=load_crm(),
                                                companies=lambda name: NOT_FOUND, seated_capacity=100)
    paths = write_outputs(tmp_path, attendees, audit, report)
    rows = read_rows(paths["attendees"])
    assert list(rows[0]) == ATTENDEE_COLUMNS
    assert json.loads(paths["report"].read_text())["attendees"] == 11
    assert json.loads(paths["audit"].read_text())[0]["step"] in {"normalize", "dedupe", "verify"}

    scores = run_part2.score(expected, rows)
    assert scores["flags"]["precision"] == scores["flags"]["recall"] == 1.0
    # The agent step has not run: three fields keep the email value, and no decision is made.
    assert scores["fields"]["correct"] == 74 and scores["fields"]["total"] == 77
    assert {m["source_keys"] for m in scores["fields"]["misses"]} == {"e07", "e08", "e10"}
    assert scores["resolutions"]["correct"] == 0


def test_brief_score():
    brief = {"answers": [{"source_ids": ["policies.csv#POL-GST-01", "venues.csv#V113"]},
                         {"source_ids": ["policies.csv#POL-DIE-01"]}],
             "deadlines": [{"policy_id": "POL-GST-01", "date": "2026-11-12"}]}
    result = run_part2.score_brief(brief)
    assert result["expected_sources_missed"] == ["policies.csv#POL-DAT-02"]
    assert result["deadlines"] == ["POL-GST-01 2026-11-12"]
    assert run_part2.score_brief({"error": "timeout"}) == {"ran": False, "error": "timeout"}
