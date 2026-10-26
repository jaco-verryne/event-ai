import json

import pytest

from eventai.rag.answer import OUT_OF_SCOPE_TEXT, SQL_FAILED_TEXT
from eventai.rag.pipeline import ask, history_text, load_resources


@pytest.fixture(scope="module")
def resources(tmp_path_factory, fake_embedder):
    return load_resources(db_path=tmp_path_factory.mktemp("db") / "events.duckdb", embedder=fake_embedder)


def plan(**fields):
    base = {
        "intent": "list",
        "tools": ["query_sql"],
        "documents": ["venues"],
        "sql": "SELECT venue_id, name FROM venues WHERE venue_id = 'V012'",
        "search_text": None,
        "standalone_question": "Which venue?",
    }
    return json.dumps({**base, **fields})


def answer(*source_ids):
    return json.dumps({
        "answer": "The Old Mill fits.",
        "facts": [{"label": "Venue", "value": "The Old Mill", "source_id": s} for s in source_ids],
        "source_ids": list(source_ids),
        "confidence": "high",
    })


def test_mixed_question_searches_only_the_sql_rows(fake_provider, resources):
    mixed = plan(
        tools=["query_sql", "search_text"],
        sql="SELECT venue_id, name FROM venues WHERE city = 'Leeds'",
        search_text="converted mill exposed brick courtyard",
    )
    groq, calls = fake_provider("groq", [mixed, answer("venues.csv#V012", "venues.csv#V999")])

    result = ask("A Leeds venue with a courtyard?", None, resources, providers=[groq])

    assert len(result.sql.record_ids) == 14
    assert result.hits and {h.record_id for h in result.hits} <= set(result.sql.record_ids)
    assert result.hits[0].record_id == "V012"
    assert [f.source_id for f in result.answer.facts] == ["venues.csv#V012"]
    assert [f.source_id for f in result.removed_facts] == ["venues.csv#V999"]
    assert "[venues.csv#V012]" in calls.calls[1]["messages"][-1]["content"]
    assert len(calls.calls) == 2  # router and answer: the budget in CLAUDE.md section 9


def test_out_of_scope_needs_one_call(fake_provider, resources):
    out = plan(intent="out_of_scope", tools=[], documents=[], sql=None)
    groq, calls = fake_provider("groq", [out])

    result = ask("What is the weather?", None, resources, providers=[groq])

    assert result.answer.answer == OUT_OF_SCOPE_TEXT
    assert result.sql is None and len(calls.calls) == 1


def test_sql_repair_then_answer(fake_provider, resources):
    bad = plan(sql="SELECT venue_id, nme FROM venues WHERE venue_id = 'V012'")
    repaired = json.dumps({"sql": "SELECT venue_id, name FROM venues WHERE venue_id = 'V012'"})
    groq, calls = fake_provider("groq", [bad, repaired, answer("venues.csv#V012")])

    result = ask("Which venue?", None, resources, providers=[groq])

    assert result.sql.repaired and result.sql.error is None
    assert "nme" in calls.calls[1]["messages"][-1]["content"]  # the error went to the repair call
    assert result.answer.facts[0].source_id == "venues.csv#V012"
    assert len(calls.calls) == 3


def test_sql_fails_twice_gives_a_fixed_answer(fake_provider, resources):
    groq, calls = fake_provider("groq", [plan(sql="SELECT nope FROM venues"), json.dumps({"sql": "DROP TABLE venues"})])

    result = ask("Which venue?", None, resources, providers=[groq])

    assert result.answer.answer == SQL_FAILED_TEXT
    assert result.answer.confidence == "low"
    assert result.sql.error and len(calls.calls) == 2


def test_empty_sql_result_means_no_search_hits(fake_provider, resources):
    mixed = plan(
        tools=["query_sql", "search_text"],
        sql="SELECT venue_id FROM venues WHERE city = 'Paris'",
        search_text="courtyard",
    )
    groq, calls = fake_provider("groq", [mixed, answer()])

    result = ask("A Paris venue with a courtyard?", None, resources, providers=[groq])

    assert result.sql.rows == [] and result.hits == []
    assert "The query returned no rows." in calls.calls[1]["messages"][-1]["content"]


def test_follow_up_sends_history_to_the_router(fake_provider, resources):
    groq, calls = fake_provider("groq", [plan(), answer("venues.csv#V012")])
    history = [
        {"role": "user", "content": "Gala dinner for 120 in Leeds?"},
        {"role": "assistant", "content": "Four venues fit."},
    ]

    ask("Which of those has parking?", history, resources, providers=[groq])

    router_message = calls.calls[0]["messages"][-1]["content"]
    assert "user: Gala dinner for 120 in Leeds?" in router_message
    assert "assistant: Four venues fit." in router_message


def test_history_text_carries_the_plan(fake_provider, resources):
    mixed = plan(
        tools=["query_sql", "search_text"],
        sql="SELECT venue_id, name FROM venues WHERE city = 'Leeds'",
        search_text="courtyard",
        standalone_question="Which Leeds venue has a courtyard?",
    )
    groq, _ = fake_provider("groq", [mixed, answer("venues.csv#V012")])
    result = ask("A Leeds venue with a courtyard?", None, resources, providers=[groq])

    text = history_text(result)

    assert text.startswith("The Old Mill fits.\nEarlier plan: ")
    assert 'question "Which Leeds venue has a courtyard?"' in text
    assert f"SQL: {result.sql.sql}" in text
    assert 'search: "courtyard"' in text


def test_follow_up_router_sees_the_earlier_sql(fake_provider, resources):
    groq, calls = fake_provider("groq", [plan(), answer("venues.csv#V012"), plan(), answer("venues.csv#V012")])
    first = ask("Which venue?", None, resources, providers=[groq])
    history = [{"role": "user", "content": "Which venue?"}, {"role": "assistant", "content": history_text(first)}]

    ask("Does it have parking?", history, resources, providers=[groq])

    assert f"SQL: {first.sql.sql}" in calls.calls[2]["messages"][-1]["content"]


def test_a_second_build_works_while_the_first_connection_is_open(fake_embedder, tmp_path):
    # Streamlit Cloud reloads code into a running process that still holds the old connection.
    from eventai.rag.loaders import build_database, connect_readonly, read_sources

    shared = tmp_path / "events.duckdb"
    old = connect_readonly(build_database(read_sources(), shared))
    try:
        first = load_resources(embedder=fake_embedder)
        second = load_resources(embedder=fake_embedder)
        assert first.con.execute("SELECT COUNT(*) FROM venues").fetchone() == (120,)
        assert second.con.execute("SELECT COUNT(*) FROM venues").fetchone() == (120,)
    finally:
        old.close()
