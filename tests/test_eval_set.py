"""The evaluation set agrees with the data (CLAUDE.md section 11)."""

from pathlib import Path

import pytest
import yaml

from eventai.rag.loaders import build_chunks, build_database, connect_readonly, read_sources

QUESTIONS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "eval" / "part1_questions.yaml").read_text()
)
TOOLS = {"query_sql", "search_text"}


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db_path = build_database(read_sources(), tmp_path_factory.mktemp("db") / "events.duckdb")
    con = connect_readonly(db_path)
    yield con
    con.close()


def result_ids(con, sql):
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    id_columns = [i for i, name in enumerate(names) if name.endswith("_id")]
    return {row[i] for row in cursor.fetchall() for i in id_columns}


def tool_sets(q):
    return [q["expected_tools"], *q.get("accepted_tools", [])]


def test_twelve_questions_with_valid_fields():
    assert [q["id"] for q in QUESTIONS] == list(range(1, 13))
    for q in QUESTIONS:
        for tools in tool_sets(q):
            assert tools and set(tools) <= TOOLS, q["id"]
        uses_sql = any("query_sql" in tools for tools in tool_sets(q))
        assert ("reference_sql" in q) == uses_sql, q["id"]
        assert isinstance(q["expected_record_ids"], list)
        assert q["expected_facts"] or q.get("expected_facts_any"), q["id"]


def test_any_of_facts_name_expected_records():
    names = {c.record_id: c.context_text for c in build_chunks(read_sources())}
    for q in QUESTIONS:
        for fact in q.get("expected_facts_any", []):
            # Each accepted answer is one of the expected records.
            assert any(f": {fact} (" in names[rid] for rid in q["expected_record_ids"]), (q["id"], fact)


def test_follow_up_points_to_an_earlier_question():
    ids = {q["id"] for q in QUESTIONS}
    for q in QUESTIONS:
        if "follow_up_of" in q:
            assert q["follow_up_of"] in ids and q["follow_up_of"] < q["id"]


@pytest.mark.parametrize("q", [q for q in QUESTIONS if "reference_sql" in q], ids=lambda q: f"q{q['id']}")
def test_reference_sql_returns_expected_records(con, q):
    found = result_ids(con, q["reference_sql"])
    expected = set(q["expected_record_ids"])
    if q["expected_tools"] == ["query_sql"]:
        assert found == expected
    else:
        assert expected <= found


def test_aggregate_facts_match_the_data(con):
    q5 = next(q for q in QUESTIONS if q["id"] == 5)
    count, lowest = con.execute(q5["reference_sql"]).fetchone()
    assert q5["expected_facts"] == [str(count), f"{lowest:,}"]


def test_search_only_records_exist():
    record_ids = {c.record_id for c in build_chunks(read_sources())}
    for q in QUESTIONS:
        assert set(q["expected_record_ids"]) <= record_ids, q["id"]
