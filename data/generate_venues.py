"""Make venues.csv from venues_input.yaml. A fixed seed gives the same file on each run."""

import argparse
import csv
import random
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEED = 42

COLUMNS = [
    "venue_id", "name", "city", "venue_type", "description",
    "seated_capacity", "standing_capacity", "day_rate_gbp", "step_free_access",
    "parking_spaces", "av_included", "catering", "nearest_station", "walk_minutes",
]

SEATED_RANGE = {
    "hotel": (80, 400),
    "conference centre": (100, 600),
    "historic house": (40, 220),
    "converted mill": (60, 250),
    "warehouse": (80, 500),
    "rooftop bar": (30, 120),
    "museum": (60, 300),
    "restaurant": (25, 120),
    "theatre": (120, 800),
    "gallery": (40, 200),
}
CITY_PRICE_FACTOR = {"London": 1.5, "Edinburgh": 1.15}
ALWAYS_IN_HOUSE = {"hotel", "restaurant"}
STATIONS = {
    "London": ["London Bridge", "King's Cross St Pancras", "Liverpool Street", "Waterloo", "Paddington", "Farringdon"],
    "Manchester": ["Manchester Piccadilly", "Manchester Victoria", "Deansgate", "Manchester Oxford Road"],
    "Leeds": ["Leeds", "Burley Park", "Headingley", "Cottingley"],
    "Birmingham": ["Birmingham New Street", "Birmingham Moor Street", "Birmingham Snow Hill", "Five Ways"],
    "Bristol": ["Bristol Temple Meads", "Clifton Down", "Lawrence Hill", "Bedminster"],
    "Liverpool": ["Liverpool Lime Street", "Liverpool Central", "Moorfields", "James Street"],
    "Edinburgh": ["Edinburgh Waverley", "Haymarket", "Edinburgh Park"],
    "Glasgow": ["Glasgow Central", "Glasgow Queen Street", "Partick", "Argyle Street"],
    "Newcastle": ["Newcastle", "Manors", "MetroCentre"],
}


def make_rows(entries: list[dict], rng: random.Random) -> list[dict]:
    ids = [f"V{n:03d}" for n in range(1, len(entries) + 1)]
    fixed_ids = [e["venue_id"] for e in entries if "venue_id" in e]
    assert len(set(fixed_ids)) == len(fixed_ids) and set(fixed_ids) <= set(ids)
    free_ids = [i for i in ids if i not in fixed_ids]
    # Shuffle so that an ID says nothing about the city.
    rng.shuffle(free_ids)
    next_id = iter(free_ids)

    rows = []
    for entry in entries:
        row = {
            "venue_id": entry.get("venue_id") or next(next_id),
            "name": entry["name"],
            "city": entry["city"],
            "venue_type": entry["venue_type"],
            "description": entry["description"],
        }
        row.update(_attributes(entry, rng))
        rows.append(row)
    return sorted(rows, key=lambda r: r["venue_id"])


def _attributes(entry: dict, rng: random.Random) -> dict:
    fixed = entry.get("fixed", {})
    city, venue_type = entry["city"], entry["venue_type"]
    # Draw every random value, even when `fixed` replaces it, so that one fixed
    # value does not change the values of the venues after it.
    lo, hi = SEATED_RANGE[venue_type]
    seated = fixed.get("seated_capacity", rng.randint(lo // 5, hi // 5) * 5)
    standing = round(seated * rng.uniform(1.3, 1.7) / 5) * 5
    day_rate = (600 + seated * rng.uniform(10, 18)) * CITY_PRICE_FACTOR.get(city, 1.0)
    no_parking_chance = 0.6 if city == "London" else 0.2
    parking = 0 if rng.random() < no_parking_chance else rng.randint(1, 24) * 5
    values = {
        "seated_capacity": seated,
        "standing_capacity": standing,
        "day_rate_gbp": int(round(day_rate / 50) * 50),
        "step_free_access": rng.random() < 0.8,
        "parking_spaces": parking,
        "av_included": rng.random() < 0.6,
        "catering": "in-house" if venue_type in ALWAYS_IN_HOUSE or rng.random() < 0.5 else "external",
        "nearest_station": rng.choice(STATIONS[city]),
        "walk_minutes": rng.randint(2, 15),
    }
    values.update(fixed)
    return values


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main(out: Path = HERE / "venues.csv") -> None:
    entries = yaml.safe_load((HERE / "venues_input.yaml").read_text())["venues"]
    rows = make_rows(entries, random.Random(SEED))
    with out.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([_cell(row[c]) for c in COLUMNS])
    print(f"Wrote {len(rows)} venues to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "venues.csv")
    main(parser.parse_args().out)
