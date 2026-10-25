import duckdb
import pytest

from eventai.rag.chunks import NOT_GIVEN
from eventai.rag.loaders import (
    TABLES,
    build_chunks,
    build_database,
    connect_readonly,
    read_sources,
)


@pytest.fixture(scope="module")
def sources():
    return read_sources()


@pytest.fixture(scope="module")
def con(sources, tmp_path_factory):
    db_path = build_database(sources, tmp_path_factory.mktemp("db") / "events.duckdb")
    con = connect_readonly(db_path)
    yield con
    con.close()


@pytest.fixture(scope="module")
def chunks(sources):
    return {c.record_id: c for c in build_chunks(sources)}


def test_tables_and_row_counts(con):
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert tables == set(TABLES)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    assert counts["venues"] == 120
    assert counts["packages"] == 8
    assert counts["policies"] == 26
    assert counts["package_items"] == 73


def test_column_types(con):
    types = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns "
                             "WHERE table_name = 'packages'").fetchall())
    assert types["suitable_venue_types"] == "VARCHAR[]"
    venue_types = dict(con.execute("SELECT column_name, data_type FROM information_schema.columns "
                                   "WHERE table_name = 'venues'").fetchall())
    assert venue_types["step_free_access"] == "BOOLEAN"
    assert venue_types["parking_spaces"] == "INTEGER"


def test_empty_value_is_null(con):
    assert con.execute("SELECT parking_spaces FROM venues WHERE venue_id = 'V045'").fetchone() == (None,)


def test_package_items_have_both_kinds(con):
    rows = dict(con.execute("SELECT kind, COUNT(*) FROM package_items GROUP BY kind").fetchall())
    assert set(rows) == {"include", "add_on"}
    priced = con.execute("SELECT COUNT(*) FROM package_items WHERE kind = 'add_on' AND price_gbp IS NULL").fetchone()
    assert priced == (0,)


def test_read_only_connection_rejects_writes(con):
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM venues")


def test_build_database_replaces_an_old_file(sources, tmp_path):
    path = tmp_path / "events.duckdb"
    build_database(sources, path)
    build_database(sources, path)
    with connect_readonly(path) as con:
        assert con.execute("SELECT COUNT(*) FROM venues").fetchone() == (120,)


def test_one_chunk_per_record(sources, chunks):
    assert len(chunks) == 120 + 8 + 26
    assert len(build_chunks(sources)) == len(chunks)  # record IDs are unique


def test_venue_chunk(chunks):
    old_mill = chunks["V012"]
    assert old_mill.chunk_id == "venues.csv#V012"
    assert old_mill.locator == "row 12"
    assert old_mill.embedding_text == (
        "The Old Mill. Converted mill. Converted Victorian mill with exposed brick and a courtyard."
    )
    assert "Day rate: £2,400 (without VAT)" in old_mill.context_text
    assert "Seated capacity: 120 guests" in old_mill.context_text


def test_embedding_text_has_no_attribute_numbers(chunks):
    assert "120" not in chunks["V012"].embedding_text
    assert "£" not in chunks["PKG-05"].embedding_text


def test_empty_value_is_named_in_context(chunks):
    v045 = chunks["V045"]
    assert f"Parking spaces: {NOT_GIVEN}" in v045.context_text
    assert "parking_spaces" not in v045.metadata


def test_package_and_policy_chunks(chunks):
    gala = chunks["PKG-05"]
    assert gala.locator == "$.packages[4]"
    assert "Price per head: £145 (without VAT)" in gala.context_text
    assert gala.metadata["suitable_venue_types"] == "hotel, historic house, converted mill, museum"

    band = chunks["POL-CAN-03"]
    assert band.embedding_text == "Cancellation 30 to 59 days before the event. 50% of the package fee is due."
    assert band.metadata == {"area": "cancellation", "applies_to": "all", "effective_from": "2026-01-01"}


def test_metadata_has_no_none_values(chunks):
    for chunk in chunks.values():
        assert all(value is not None for value in chunk.metadata.values()), chunk.chunk_id
