"""What the Knowledge base page shows: the three documents, the tables built from them, and their
chunks. Plain functions, so the page file stays thin and this logic has tests."""

from collections.abc import Sequence
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from eventai.rag.chunks import Chunk
from eventai.rag.loaders import DATA_DIR, TABLES


@dataclass(frozen=True)
class DocumentInfo:
    key: str  # the router's document name
    file: str
    title: str
    brief_example: str  # the brief's example of a structured document
    about: str
    text_fields: tuple[str, ...]  # embedded for the vector search, and indexed for BM25
    attribute_fields: tuple[str, ...]  # filtered and counted with SQL
    test_cases: tuple[str, ...]
    tables: tuple[str, ...]  # the DuckDB tables that the loader builds from the file
    mime: str
    default_record: str  # the record that the chunk view shows first


DOCUMENTS = (
    DocumentInfo(
        key="venues",
        file="venues.csv",
        title="Venues",
        brief_example="Dataset",
        about=(
            "One row for each partner venue in nine UK cities. A script makes the file from hand-written "
            "names and descriptions, with a fixed random seed, so each run gives the same data."
        ),
        text_fields=("name", "venue_type", "description"),
        attribute_fields=(
            "venue_id", "city", "seated_capacity", "standing_capacity", "day_rate_gbp",
            "step_free_access", "parking_spaces", "av_included", "catering", "nearest_station",
            "walk_minutes",
        ),
        test_cases=(
            "Two similar names: The Old Mill (Leeds, V012) and Old Mill Studios (Manchester).",
            "V045 has no parking value. The answer must say that the data does not give it.",
            "Leeds venues with a courtyard, a terrace, a garden or lawns. No description uses the word "
            "\"outdoor\", so only the meaning search finds them.",
            "Manchester venues on the limit of 150 seats, with and without step-free access.",
        ),
        tables=("venues",),
        mime="text/csv",
        default_record="V012",
    ),
    DocumentInfo(
        key="packages",
        file="packages.json",
        title="Packages",
        brief_example="Product specifications",
        about=(
            "One object for each event package, with two nested lists: the included items and the paid "
            "add-ons. The loader makes two tables from the file: packages, and package_items (one row "
            "for each included item or add-on)."
        ),
        text_fields=("name", "description", "includes", "add_ons"),
        attribute_fields=(
            "package_id", "event_type", "min_guests", "max_guests", "price_per_head_gbp",
            "lead_time_weeks", "suitable_venue_types",
        ),
        test_cases=(
            "Two IDs one character apart: PKG-01 and PKG-07.",
            "suitable_venue_types links each package to the venue types, so one question can join "
            "packages and venues.",
            "Prices exclude VAT.",
        ),
        tables=("packages", "package_items"),
        mime="application/json",
        default_record="PKG-05",
    ),
    DocumentInfo(
        key="policies",
        file="policies.csv",
        title="Policies",
        brief_example="Policy table",
        about=(
            "One row for each booking rule: cancellation, deposit, payment, guest numbers, dietary needs, "
            "access and data retention. The condition and the rule are text, so the answer step reads them "
            "and picks the rule that matches."
        ),
        text_fields=("condition", "rule"),
        attribute_fields=("policy_id", "area", "applies_to", "effective_from"),
        test_cases=(
            "Cancellation bands with exact limits: a cancellation 30 days before the event falls in "
            "one band only.",
            "One rule for one package only: final guest numbers for the Gala Dinner (PKG-05) are due "
            "earlier than for other packages.",
        ),
        tables=("policies",),
        mime="text/csv",
        default_record="POL-CAN-04",
    ),
)


def table_frame(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    """One table as the SQL sees it, in file order. A list cell becomes comma-joined text."""
    if table not in TABLES:  # the name comes from DOCUMENTS, never from a user
        raise ValueError(f"Unknown table: {table}")
    frame = con.execute(f"SELECT * FROM {table} ORDER BY rowid").df()
    for column in frame.columns:
        if frame[column].map(lambda v: isinstance(v, (list, np.ndarray))).any():
            frame[column] = frame[column].map(lambda v: ", ".join(map(str, v)))
    return frame


def document_chunks(chunks: Sequence[Chunk], document: DocumentInfo) -> list[Chunk]:
    return [c for c in chunks if c.source == document.file]


def raw_file(document: DocumentInfo) -> bytes:
    return (DATA_DIR / document.file).read_bytes()
