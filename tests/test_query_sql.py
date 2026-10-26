"""One or more tests for each SQL guardrail in CLAUDE.md section 8."""

import time
from pathlib import Path

import duckdb
import pytest
import yaml

from eventai.rag import query_sql as q
from eventai.rag.loaders import build_database, connect_readonly, read_sources
from eventai.rag.query_sql import SqlRejected, SqlTimeout, check_sql, query_sql, run_with_timeout

QUESTIONS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "eval" / "part1_questions.yaml").read_text()
)


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    con = connect_readonly(build_database(read_sources(), tmp_path_factory.mktemp("db") / "events.duckdb"))
    yield con
    con.close()


# Rule 1: read-only, and no file access even past the SQL check.


def test_rule1_connection_is_read_only(con):
    with pytest.raises(duckdb.Error):
        con.execute("UPDATE venues SET city = 'Paris'")


def test_rule1_connection_cannot_read_files(con):
    with pytest.raises(duckdb.Error, match="disabled"):
        con.execute("SELECT * FROM read_csv('data/venues.csv')")


# Rule 2: exactly one statement, and only a SELECT.


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT venue_id FROM venues; DROP TABLE venues",
        "DROP TABLE venues",
        "DELETE FROM venues",
        "INSERT INTO venues (venue_id) VALUES ('V999')",
        "COPY venues TO 'out.csv'",
        "ATTACH 'other.db'",
        "PRAGMA show_tables",
        "SET memory_limit = '1GB'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "CREATE TABLE t AS SELECT * FROM venues",
    ],
)
def test_rule2_only_one_select(sql):
    with pytest.raises(SqlRejected):
        check_sql(sql)


def test_rule2_select_union_and_comments_pass():
    check_sql("SELECT venue_id FROM venues UNION SELECT package_id FROM packages")
    tree = check_sql("SELECT venue_id FROM venues -- ; DROP TABLE venues")
    assert "DROP" not in tree.sql(dialect="duckdb", comments=False)


def test_rule2_unparsable_sql_is_rejected():
    with pytest.raises(SqlRejected, match="parse"):
        check_sql("SELEC venue_id FROM")


# Rule 3: known tables and columns only; no table functions.


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT * FROM users", "Unknown table"),
        ("SELECT * FROM read_csv('data/venues.csv')", "Table functions"),
        ("SELECT * FROM range(10)", "Table functions"),
        ("SELECT * FROM 'data/venues.csv'", "Unknown table"),
        ("SELECT * FROM main.venues", "schema"),
        ("SELECT password FROM venues", "Unknown column"),
    ],
)
def test_rule3_unknown_tables_columns_and_functions(sql, message):
    with pytest.raises(SqlRejected, match=message):
        check_sql(sql)


def test_rule3_ctes_and_aliases_pass():
    check_sql("WITH leeds AS (SELECT venue_id FROM venues WHERE city = 'Leeds') SELECT venue_id FROM leeds")
    check_sql("SELECT city, COUNT(*) AS n FROM venues GROUP BY city ORDER BY n DESC")
    check_sql("SELECT v.* FROM venues AS v")


@pytest.mark.parametrize("item", [x for x in QUESTIONS if "reference_sql" in x], ids=lambda x: f"q{x['id']}")
def test_rule3_reference_sql_passes_and_regeneration_keeps_rows(con, item):
    tree = check_sql(item["reference_sql"])
    raw = sorted(map(str, con.execute(item["reference_sql"]).fetchall()))
    regenerated = sorted(map(str, con.execute(tree.sql(dialect="duckdb", comments=False)).fetchall()))
    assert regenerated == raw


# Rule 4: row limit of 200.


def test_rule4_row_limit(con, monkeypatch):
    monkeypatch.setattr(q, "MAX_ROWS", 50)
    result = query_sql(con, "SELECT venue_id FROM venues")
    assert len(result.rows) == 50
    assert result.truncated


def test_rule4_full_result_under_the_limit_keeps_order(con):
    result = query_sql(con, "SELECT venue_id, day_rate_gbp FROM venues ORDER BY day_rate_gbp DESC")
    assert len(result.rows) == 120 and not result.truncated
    rates = [row[1] for row in result.rows]
    assert rates == sorted(rates, reverse=True)
    assert result.sql.startswith("SELECT venue_id")


# Rule 5: timeout with interrupt.


def test_rule5_slow_query_is_interrupted(con):
    start = time.monotonic()
    with pytest.raises(SqlTimeout):
        run_with_timeout(con, "SELECT COUNT(*) FROM range(20000000000)", seconds=0.2)
    assert time.monotonic() - start < 2
    assert con.execute("SELECT COUNT(*) FROM venues").fetchone() == (120,)  # connection still works


# Rule 6: one repair, then give up.


def test_rule6_one_repair_fixes_the_query(con):
    calls = []

    def repair(sql, error):
        calls.append((sql, error))
        return "SELECT venue_id, name FROM venues WHERE venue_id = 'V012'"

    result = query_sql(con, "SELECT venue_id, nme FROM venues", repair)

    assert len(calls) == 1 and "nme" in calls[0][1]
    assert result.repaired and result.error is None
    assert result.first_error and result.record_ids == ["V012"]


def test_rule6_second_error_gives_up(con):
    calls = []

    def repair(sql, error):
        calls.append(error)
        return "SELECT still_wrong FROM venues"

    result = query_sql(con, "DROP TABLE venues", repair)

    assert len(calls) == 1
    assert result.error and "still_wrong" in result.error
    assert result.rows == [] and result.repaired


def test_rule6_runtime_error_is_repaired(con):
    result = query_sql(
        con,
        "SELECT venue_id FROM venues WHERE seated_capacity = 'many'",
        lambda sql, error: "SELECT venue_id FROM venues WHERE seated_capacity >= 700",
    )
    assert result.repaired and result.error is None


def test_error_without_repair(con):
    result = query_sql(con, "SELECT * FROM users")
    assert result.error and not result.repaired and result.rows == []


# Citations from the result.


def test_source_ids_for_rows_and_joins(con):
    result = query_sql(
        con,
        "SELECT v.venue_id, p.package_id FROM venues v JOIN packages p "
        "ON list_contains(p.suitable_venue_types, v.venue_type) "
        "WHERE v.venue_id = 'V012' AND p.package_id = 'PKG-05'",
    )
    assert result.record_ids == ["V012", "PKG-05"]
    assert result.source_ids == ["venues.csv#V012", "packages.json#PKG-05"]


def test_source_ids_for_aggregates_and_empty_results(con):
    aggregate = query_sql(con, "SELECT COUNT(*) AS n FROM venues WHERE city = 'London'")
    assert aggregate.rows == [[20]] and aggregate.source_ids == ["venues.csv"]
    empty = query_sql(con, "SELECT venue_id FROM venues WHERE city = 'Paris'")
    assert empty.rows == [] and empty.source_ids == ["venues.csv"]


def test_values_are_json_safe(con):
    result = query_sql(con, "SELECT policy_id, effective_from FROM policies WHERE policy_id = 'POL-GST-02'")
    assert result.rows == [["POL-GST-02", "2026-04-01"]]
    lists = query_sql(con, "SELECT package_id, suitable_venue_types FROM packages WHERE package_id = 'PKG-05'")
    assert lists.rows[0][1] == ["hotel", "historic house", "converted mill", "museum"]
