"""One chunk per record: the text fields to embed, and the full record for the answer step."""

from pydantic import BaseModel

NOT_GIVEN = "not given in the data"


class Chunk(BaseModel):
    chunk_id: str  # "venues.csv#V012"
    source: str  # "venues.csv"
    record_id: str  # "V012"
    locator: str  # "row 12" or "$.packages[2]"
    embedding_text: str
    context_text: str
    metadata: dict[str, str | int | float | bool]


def venue_chunk(row: dict, row_number: int) -> Chunk:
    station = row["nearest_station"]
    if station and row["walk_minutes"] is not None:
        station = f"{station}, {row['walk_minutes']} minutes on foot"
    return Chunk(
        chunk_id=f"venues.csv#{row['venue_id']}",
        source="venues.csv",
        record_id=row["venue_id"],
        locator=f"row {row_number}",
        embedding_text=f"{row['name']}. {row['venue_type'].capitalize()}. {row['description']}",
        context_text=_context(
            f"Source: venues.csv | ID: {row['venue_id']} | Row: {row_number}",
            ("Venue", f"{row['name']} ({row['city']})"),
            ("Type", row["venue_type"]),
            ("Description", row["description"]),
            ("Seated capacity", _guests(row["seated_capacity"])),
            ("Standing capacity", _guests(row["standing_capacity"])),
            ("Day rate", _gbp(row["day_rate_gbp"])),
            ("Step-free access", _yes_no(row["step_free_access"])),
            ("Parking spaces", row["parking_spaces"]),
            ("AV included", _yes_no(row["av_included"])),
            ("Catering", row["catering"]),
            ("Nearest station", station),
        ),
        metadata=_metadata(
            row,
            ["city", "venue_type", "seated_capacity", "standing_capacity", "day_rate_gbp",
             "step_free_access", "parking_spaces", "av_included", "catering", "walk_minutes"],
        ),
    )


def package_chunk(package: dict, index: int) -> Chunk:
    includes = "; ".join(package["includes"])
    add_on_names = "; ".join(a["name"] for a in package["add_ons"])
    add_ons = "; ".join(f"{a['name']} (£{a['price_gbp']:,})" for a in package["add_ons"])
    return Chunk(
        chunk_id=f"packages.json#{package['package_id']}",
        source="packages.json",
        record_id=package["package_id"],
        locator=f"$.packages[{index}]",
        embedding_text=(
            f"{package['name']}. {package['description']} "
            f"Includes: {includes}. Add-ons: {add_on_names}."
        ),
        context_text=_context(
            f"Source: packages.json | ID: {package['package_id']} | Path: $.packages[{index}]",
            ("Package", f"{package['name']} ({package['package_id']})"),
            ("Event type", package["event_type"]),
            ("Description", package["description"]),
            ("Guests", f"{package['min_guests']} to {package['max_guests']}"),
            ("Price per head", _gbp(package["price_per_head_gbp"])),
            ("Includes", includes),
            ("Add-ons (prices without VAT)", add_ons),
            ("Lead time", f"{package['lead_time_weeks']} weeks"),
            ("Suitable venue types", ", ".join(package["suitable_venue_types"])),
        ),
        metadata=_metadata(
            {**package, "suitable_venue_types": ", ".join(package["suitable_venue_types"])},
            ["event_type", "min_guests", "max_guests", "price_per_head_gbp",
             "lead_time_weeks", "suitable_venue_types"],
        ),
    )


def policy_chunk(row: dict, row_number: int) -> Chunk:
    applies_to = "all packages" if row["applies_to"] == "all" else row["applies_to"]
    return Chunk(
        chunk_id=f"policies.csv#{row['policy_id']}",
        source="policies.csv",
        record_id=row["policy_id"],
        locator=f"row {row_number}",
        embedding_text=f"{row['condition']}. {row['rule']}",
        context_text=_context(
            f"Source: policies.csv | ID: {row['policy_id']} | Row: {row_number}",
            ("Policy area", row["area"]),
            ("Applies to", applies_to),
            ("Condition", row["condition"]),
            ("Rule", row["rule"]),
            ("Effective from", row["effective_from"]),
        ),
        metadata=_metadata(
            {**row, "effective_from": str(row["effective_from"])},
            ["area", "applies_to", "effective_from"],
        ),
    )


def _context(header: str, *pairs: tuple[str, object]) -> str:
    lines = [header]
    for label, value in pairs:
        lines.append(f"{label}: {NOT_GIVEN if value in (None, '') else value}")
    return "\n".join(lines)


def _metadata(record: dict, fields: list[str]) -> dict:
    # Chroma rejects None values, so an empty attribute is left out.
    return {f: record[f] for f in fields if record.get(f) is not None}


def _gbp(amount: int | None) -> str | None:
    return None if amount is None else f"£{amount:,} (without VAT)"


def _guests(count: int | None) -> str | None:
    return None if count is None else f"{count} guests"


def _yes_no(flag: bool | None) -> str | None:
    return None if flag is None else ("yes" if flag else "no")
