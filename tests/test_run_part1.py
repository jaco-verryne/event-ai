"""The scorer's fact check (eval/run_part1.py)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_part1", Path(__file__).resolve().parent.parent / "eval" / "run_part1.py"
)
run_part1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_part1)


def test_fact_score_ignores_case_pounds_and_commas():
    q = {"expected_facts": ["20", "2,250"]}
    assert run_part1.fact_score(q, "There are 20 venues; the lowest day rate is £2250.") == (["20", "2,250"], 2)


def test_fact_score_counts_any_of_as_one_fact():
    q = {"expected_facts": [], "expected_facts_any": ["The Old Mill", "Roundhay Hall"]}
    assert run_part1.fact_score(q, "Roundhay Hall has formal lawns.") == (["Roundhay Hall"], 1)
    assert run_part1.fact_score(q, "Calder Works is a warehouse.") == ([], 1)


def test_fact_score_mixes_both_kinds():
    q = {"expected_facts": ["does not give"], "expected_facts_any": ["V045", "Headingley Assembly Rooms"]}
    found, total = run_part1.fact_score(q, "The data does not give the parking for Headingley Assembly Rooms.")
    assert found == ["does not give", "Headingley Assembly Rooms"] and total == 2


Q10 = {"expected_tools": ["query_sql"], "expected_record_ids": ["V012", "V024", "V045", "V064"]}
REFERENCE = (["venue_id", "name", "parking_spaces"], [("V012", "a", 20), ("V024", "b", 0), ("V045", "c", None), ("V064", "d", 35)])


def test_extra_id_column_from_a_join_still_matches():
    result = (["venue_id", "name", "parking_spaces", "package_id"],
              [["V012", "a", 20, "PKG-05"], ["V024", "b", 0, "PKG-05"], ["V045", "c", None, "PKG-05"], ["V064", "d", 35, "PKG-05"]])
    assert run_part1.sql_matches(Q10, result, REFERENCE)


def test_missing_or_extra_rows_do_not_match():
    missing = (["venue_id"], [["V012"], ["V024"], ["V064"]])
    extra = (["venue_id"], [["V012"], ["V024"], ["V045"], ["V064"], ["V062"]])
    assert not run_part1.sql_matches(Q10, missing, REFERENCE)
    assert not run_part1.sql_matches(Q10, extra, REFERENCE)
