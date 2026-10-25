"""Read the three knowledge base files once, then make the DuckDB tables and the chunks."""

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from eventai.rag.chunks import Chunk, package_chunk, policy_chunk, venue_chunk

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "events.duckdb"

# Column name -> DuckDB type. The CSV reader converts values with the same types.
VENUE_COLUMNS = {
    "venue_id": "VARCHAR",
    "name": "VARCHAR",
    "city": "VARCHAR",
    "venue_type": "VARCHAR",
    "description": "VARCHAR",
    "seated_capacity": "INTEGER",
    "standing_capacity": "INTEGER",
    "day_rate_gbp": "INTEGER",
    "step_free_access": "BOOLEAN",
    "parking_spaces": "INTEGER",
    "av_included": "BOOLEAN",
    "catering": "VARCHAR",
    "nearest_station": "VARCHAR",
    "walk_minutes": "INTEGER",
}
POLICY_COLUMNS = {
    "policy_id": "VARCHAR",
    "area": "VARCHAR",
    "applies_to": "VARCHAR",
    "condition": "VARCHAR",
    "rule": "VARCHAR",
    "effective_from": "DATE",
}
PACKAGE_COLUMNS = {
    "package_id": "VARCHAR",
    "name": "VARCHAR",
    "event_type": "VARCHAR",
    "description": "VARCHAR",
    "min_guests": "INTEGER",
    "max_guests": "INTEGER",
    "price_per_head_gbp": "INTEGER",
    "lead_time_weeks": "INTEGER",
    "suitable_venue_types": "VARCHAR[]",
}
PACKAGE_ITEM_COLUMNS = {
    "package_id": "VARCHAR",
    "kind": "VARCHAR",  # "include" or "add_on"
    "name": "VARCHAR",
    "price_gbp": "INTEGER",  # add-ons only
}
TABLES = {
    "venues": VENUE_COLUMNS,
    "policies": POLICY_COLUMNS,
    "packages": PACKAGE_COLUMNS,
    "package_items": PACKAGE_ITEM_COLUMNS,
}


@dataclass(frozen=True)
class Sources:
    venues: list[dict]
    policies: list[dict]
    packages: list[dict]


def read_sources(data_dir: Path = DATA_DIR) -> Sources:
    return Sources(
        venues=_read_csv(data_dir / "venues.csv", VENUE_COLUMNS),
        policies=_read_csv(data_dir / "policies.csv", POLICY_COLUMNS),
        packages=json.loads((data_dir / "packages.json").read_text())["packages"],
    )


def build_database(sources: Sources, db_path: Path = DB_PATH) -> Path:
    """Write a new database file. The app then opens it with connect_readonly()."""
    db_path.unlink(missing_ok=True)
    Path(f"{db_path}.wal").unlink(missing_ok=True)
    rows = {
        "venues": sources.venues,
        "policies": sources.policies,
        "packages": sources.packages,
        "package_items": list(_package_items(sources.packages)),
    }
    con = duckdb.connect(str(db_path))
    try:
        for table, columns in TABLES.items():
            _create_table(con, table, columns, rows[table])
    finally:
        con.close()
    return db_path


def connect_readonly(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    # Guardrail 1: the LLM-written SQL can never change the data.
    return duckdb.connect(str(db_path), read_only=True)


def build_chunks(sources: Sources) -> list[Chunk]:
    return [
        *(venue_chunk(row, n) for n, row in enumerate(sources.venues, start=1)),
        *(package_chunk(p, i) for i, p in enumerate(sources.packages)),
        *(policy_chunk(row, n) for n, row in enumerate(sources.policies, start=1)),
    ]


def _read_csv(path: Path, columns: dict[str, str]) -> list[dict]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(columns):
            raise ValueError(f"{path.name}: columns {reader.fieldnames} are not {list(columns)}")
        return [{name: _convert(row[name], kind) for name, kind in columns.items()} for row in reader]


def _convert(text: str, kind: str):
    if text == "":
        return None
    if kind == "INTEGER":
        return int(text)
    if kind == "BOOLEAN":
        if text not in ("true", "false"):
            raise ValueError(f"not a boolean: {text!r}")
        return text == "true"
    if kind == "DATE":
        return date.fromisoformat(text)
    return text


def _package_items(packages: list[dict]):
    for p in packages:
        for name in p["includes"]:
            yield {"package_id": p["package_id"], "kind": "include", "name": name, "price_gbp": None}
        for add_on in p["add_ons"]:
            yield {
                "package_id": p["package_id"],
                "kind": "add_on",
                "name": add_on["name"],
                "price_gbp": add_on["price_gbp"],
            }


def _create_table(con, table: str, columns: dict[str, str], rows: list[dict]) -> None:
    con.execute(f"CREATE TABLE {table} ({', '.join(f'{n} {t}' for n, t in columns.items())})")
    placeholders = ", ".join("?" for _ in columns)
    con.executemany(
        f"INSERT INTO {table} VALUES ({placeholders})",
        [[row[n] for n in columns] for row in rows],
    )
