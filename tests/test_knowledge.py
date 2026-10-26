import csv
import json

import pandas as pd
import pytest

from eventai.rag.knowledge import DOCUMENTS, document_chunks, raw_file, table_frame
from eventai.rag.loaders import DATA_DIR, TABLES, build_chunks, build_database, connect_readonly, read_sources
from eventai.rag.search_text import DOCUMENTS as SEARCH_DOCUMENTS


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    con = connect_readonly(build_database(read_sources(), tmp_path_factory.mktemp("db") / "events.duckdb"))
    yield con
    con.close()


def file_fields(file):
    if file.endswith(".csv"):
        with (DATA_DIR / file).open(newline="") as f:
            return set(next(csv.reader(f)))
    return set(json.loads((DATA_DIR / file).read_text())["packages"][0])


def test_one_tab_per_document_with_real_tables():
    assert {d.file: d.key for d in DOCUMENTS} == SEARCH_DOCUMENTS
    for document in DOCUMENTS:
        assert set(document.tables) <= set(TABLES)


def test_listed_fields_exist_in_each_file():
    for document in DOCUMENTS:
        fields = file_fields(document.file)
        assert set(document.text_fields) | set(document.attribute_fields) <= fields, document.file
        assert not set(document.text_fields) & set(document.attribute_fields)


def test_table_frames_show_all_rows_in_file_order(con):
    counts = {table: len(table_frame(con, table)) for d in DOCUMENTS for table in d.tables}
    assert counts == {"venues": 120, "packages": 8, "package_items": 73, "policies": 26}

    venues = table_frame(con, "venues")
    assert venues["venue_id"].iloc[0] == "V001"
    assert pd.isna(venues.loc[venues["venue_id"] == "V045", "parking_spaces"].iloc[0])

    policies = table_frame(con, "policies")
    assert policies["policy_id"].iloc[0] == "POL-CAN-01"


def test_list_cells_become_text(con):
    packages = table_frame(con, "packages")
    gala = packages.loc[packages["package_id"] == "PKG-05", "suitable_venue_types"].iloc[0]
    assert gala == "hotel, historic house, converted mill, museum"


def test_only_known_tables(con):
    with pytest.raises(ValueError):
        table_frame(con, "venues; DROP TABLE venues")


def test_chunks_per_document_and_default_records():
    chunks = build_chunks(read_sources())
    for document in DOCUMENTS:
        own = document_chunks(chunks, document)
        assert {c.source for c in own} == {document.file}
        assert document.default_record in {c.record_id for c in own}
    assert len(document_chunks(chunks, DOCUMENTS[0])) == 120


def test_raw_file_is_the_committed_file():
    for document in DOCUMENTS:
        assert raw_file(document) == (DATA_DIR / document.file).read_bytes()
