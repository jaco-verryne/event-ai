"""The knowledge base files hold the agreed columns and each test case (CLAUDE.md section 6)."""

import csv
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"

VENUE_COLUMNS = [
    "venue_id", "name", "city", "venue_type", "description",
    "seated_capacity", "standing_capacity", "day_rate_gbp", "step_free_access",
    "parking_spaces", "av_included", "catering", "nearest_station", "walk_minutes",
]
POLICY_COLUMNS = ["policy_id", "area", "applies_to", "condition", "rule", "effective_from"]
PACKAGE_KEYS = {
    "package_id", "name", "event_type", "description", "min_guests", "max_guests",
    "price_per_head_gbp", "includes", "add_ons", "lead_time_weeks", "suitable_venue_types",
}


def read_csv(name):
    with (DATA / name).open(newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


@pytest.fixture(scope="module")
def venues():
    columns, rows = read_csv("venues.csv")
    assert columns == VENUE_COLUMNS
    return rows


@pytest.fixture(scope="module")
def policies():
    columns, rows = read_csv("policies.csv")
    assert columns == POLICY_COLUMNS
    return rows


@pytest.fixture(scope="module")
def packages():
    return json.loads((DATA / "packages.json").read_text())["packages"]


def test_sizes_and_unique_ids(venues, policies, packages):
    assert len(venues) == 120
    assert 20 <= len(policies) <= 30
    assert len(packages) == 8
    for rows, key in ((venues, "venue_id"), (policies, "policy_id"), (packages, "package_id")):
        ids = [r[key] for r in rows]
        assert len(ids) == len(set(ids))


def test_package_shape(packages):
    for p in packages:
        assert set(p) == PACKAGE_KEYS
        assert p["min_guests"] < p["max_guests"]
        assert all(set(a) == {"name", "price_gbp"} for a in p["add_ons"])


def test_shared_keys_link_the_documents(venues, policies, packages):
    venue_types = {v["venue_type"] for v in venues}
    package_ids = {p["package_id"] for p in packages}
    for p in packages:
        assert set(p["suitable_venue_types"]) <= venue_types
    for rule in policies:
        assert rule["applies_to"] == "all" or rule["applies_to"] in package_ids


def test_case_1_similar_venue_names(venues):
    by_name = {v["name"]: v for v in venues}
    assert by_name["The Old Mill"]["city"] == "Leeds"
    assert by_name["Old Mill Studios"]["city"] == "Manchester"


def test_case_2_package_ids_one_character_apart(packages):
    ids = {p["package_id"] for p in packages}
    assert {"PKG-01", "PKG-07"} <= ids


def test_case_3_only_v045_has_no_parking_value(venues):
    assert [v["venue_id"] for v in venues if v["parking_spaces"] == ""] == ["V045"]


def _band(condition):
    if m := re.search(r"(\d+) to (\d+) days", condition):
        return int(m[1]), int(m[2])
    if m := re.search(r"(\d+) days or more", condition):
        return int(m[1]), math.inf
    if m := re.search(r"fewer than (\d+) days", condition):
        return 0, int(m[1]) - 1
    return None


def test_case_4_each_day_falls_in_one_cancellation_band(policies):
    bands = [_band(p["condition"]) for p in policies if p["area"] == "cancellation"]
    bands = [b for b in bands if b]
    assert len(bands) == 4
    for day in range(0, 401):
        assert sum(lo <= day <= hi for lo, hi in bands) == 1, day


def test_case_5_gala_dinner_guest_numbers_rule(policies, packages):
    gala = next(p for p in packages if p["name"] == "Gala Dinner")
    rules = [p for p in policies if p["area"] == "guest numbers"]
    scoped = [p for p in rules if p["applies_to"] != "all"]
    assert [p["applies_to"] for p in scoped] == [gala["package_id"]]
    assert any(p["applies_to"] == "all" and p["condition"] == "Final guest numbers" for p in rules)


def test_case_6_leeds_space_to_enjoy_without_the_word_outdoor(venues):
    leeds = [v["description"].lower() for v in venues if v["city"] == "Leeds"]
    with_space = [d for d in leeds if re.search(r"courtyard|terrace|garden", d)]
    assert len(with_space) >= 3
    assert not any("outdoor" in v["description"].lower() for v in venues)


def test_prices_are_whole_pounds(venues, packages):
    assert all(v["day_rate_gbp"].isdigit() for v in venues)
    assert all(isinstance(p["price_per_head_gbp"], int) for p in packages)


def test_generator_is_repeatable(tmp_path):
    spec = importlib.util.spec_from_file_location("generate_venues", DATA / "generate_venues.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    out = tmp_path / "venues.csv"
    generator.main(out)

    assert out.read_bytes() == (DATA / "venues.csv").read_bytes()
