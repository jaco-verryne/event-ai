import json

from eventai.rag.answer import (
    VAT_NOTE,
    Answer,
    Fact,
    allowed_source_ids,
    answer_question,
    check_citations,
    tool_context,
)
from eventai.rag.chunks import NOT_GIVEN
from eventai.rag.query_sql import SqlResult
from eventai.rag.search_text import SearchHit

SQL = SqlResult(
    sql="SELECT venue_id, name, parking_spaces FROM venues",
    columns=["venue_id", "name", "parking_spaces"],
    rows=[["V012", "The Old Mill", 20], ["V045", "Headingley Assembly Rooms", None]],
    record_ids=["V012", "V045"],
    source_ids=["venues.csv#V012", "venues.csv#V045"],
)
HIT = SearchHit(
    chunk_id="packages.json#PKG-05",
    source="packages.json",
    record_id="PKG-05",
    score=0.03,
    vector_similarity=0.7,
    bm25_score=None,
    vector_rank=1,
    bm25_rank=None,
    context_text="Source: packages.json | ID: PKG-05\nPrice per head: £145 (without VAT)",
)


def make_answer(**fields):
    base = {
        "answer": "The Old Mill has 20 parking spaces.",
        "facts": [{"label": "Parking spaces", "value": "20", "source_id": "venues.csv#V012"}],
        "source_ids": ["venues.csv#V012"],
        "confidence": "high",
    }
    return Answer(**{**base, **fields})


def test_context_shows_row_sources_and_empty_values():
    text = tool_context(SQL, [HIT])
    assert "SQL: SELECT venue_id, name, parking_spaces FROM venues" in text
    assert "[venues.csv#V012] venue_id: V012 | name: The Old Mill | parking_spaces: 20" in text
    assert f"[venues.csv#V045] venue_id: V045 | name: Headingley Assembly Rooms | parking_spaces: {NOT_GIVEN}" in text
    assert "[packages.json#PKG-05]\nSource: packages.json | ID: PKG-05" in text


def test_context_for_aggregates_empty_results_errors_and_no_hits():
    aggregate = SqlResult(sql="SELECT COUNT(*) AS n FROM venues", columns=["n"], rows=[[20]], source_ids=["venues.csv"])
    assert "[venues.csv] n: 20" in tool_context(aggregate, [])
    empty = SqlResult(sql="SELECT venue_id FROM venues WHERE city = 'Paris'", source_ids=["venues.csv"])
    assert "The query returned no rows." in tool_context(empty, [])
    failed = SqlResult(sql="SELECT nope FROM venues", error="Unknown column 'nope'.")
    assert "The query failed twice: Unknown column 'nope'." in tool_context(failed, [])
    assert "no text matched" in tool_context(None, [], searched=True)
    truncated = SQL.model_copy(update={"truncated": True})
    assert "only the first 2 are shown" in tool_context(truncated, [])


def test_allowed_source_ids():
    assert allowed_source_ids(SQL, [HIT]) == ["venues.csv#V012", "venues.csv#V045", "packages.json#PKG-05"]
    failed = SQL.model_copy(update={"error": "failed"})
    assert allowed_source_ids(failed, [HIT]) == ["packages.json#PKG-05"]


def test_citation_check_removes_invented_ids():
    answer = make_answer(
        facts=[
            {"label": "Parking spaces", "value": "20", "source_id": "venues.csv#V012"},
            {"label": "Parking spaces", "value": "50", "source_id": "venues.csv#V999"},
        ],
        source_ids=["venues.csv#V012", "venues.csv#V999"],
    )

    checked, removed = check_citations(answer, allowed_source_ids(SQL, []))

    assert [f.source_id for f in checked.facts] == ["venues.csv#V012"]
    assert removed == [Fact(label="Parking spaces", value="50", source_id="venues.csv#V999")]
    assert checked.source_ids == ["venues.csv#V012"]
    assert checked.confidence == "high"


def test_cited_facts_are_added_to_source_ids():
    checked, _ = check_citations(make_answer(source_ids=[]), ["venues.csv#V012"])
    assert checked.source_ids == ["venues.csv#V012"]


def test_all_facts_removed_gives_low_confidence():
    checked, removed = check_citations(make_answer(), ["venues.csv#V045"])
    assert checked.facts == [] and len(removed) == 1
    assert checked.confidence == "low"


def test_vat_note_is_added_once():
    priced = make_answer(answer="The Gala Dinner costs £145 per head.")
    checked, _ = check_citations(priced, ["venues.csv#V012"])
    assert checked.answer.endswith(VAT_NOTE)

    already = make_answer(answer="The Gala Dinner costs £145 per head, without VAT.")
    checked, _ = check_citations(already, ["venues.csv#V012"])
    assert checked.answer == already.answer

    fact_price = make_answer(facts=[{"label": "Price", "value": "£145", "source_id": "venues.csv#V012"}])
    checked, _ = check_citations(fact_price, ["venues.csv#V012"])
    assert checked.answer.endswith(VAT_NOTE)


def test_answer_question_sends_question_results_and_allowed_ids(fake_provider):
    groq, calls = fake_provider("groq", [make_answer().model_dump_json()])

    result = answer_question("How much parking?", SQL, [HIT], providers=[groq])

    assert result == make_answer()
    user = calls.calls[0]["messages"][-1]["content"]
    assert user.startswith("Question: How much parking?")
    assert "Allowed source IDs: venues.csv#V012, venues.csv#V045, packages.json#PKG-05" in user
    system = "\n".join(m["content"] for m in calls.calls[0]["messages"] if m["role"] == "system")
    assert "Use only the tool results" in system
    assert json.loads(calls.calls[0]["messages"][0]["content"].split("\n", 1)[1])["title"] == "Answer"
