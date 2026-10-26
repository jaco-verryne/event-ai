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
