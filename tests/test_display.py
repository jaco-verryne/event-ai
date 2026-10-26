import httpx2
import openai

from eventai.llm import DailyLimitReached, InvalidOutput, ProviderError
from eventai.rag.answer import Answer
from eventai.rag.chunks import NOT_GIVEN
from eventai.rag.display import (
    INVALID_TEXT,
    LIMIT_TEXT,
    OTHER_TEXT,
    SERVICE_TEXT,
    cited_sources,
    error_message,
    fact_rows,
    hit_rows,
    router_history,
    sql_rows,
)
from eventai.rag.loaders import build_chunks, read_sources
from eventai.rag.pipeline import PipelineResult
from eventai.rag.query_sql import SqlResult
from eventai.rag.router import RouterPlan
from eventai.rag.search_text import SearchHit

PLAN = RouterPlan(
    intent="aggregate", tools=["query_sql"], documents=["venues"],
    sql="SELECT COUNT(*) FROM venues", standalone_question="How many?",
)
ANSWER = Answer(
    answer="There are 20 London venues. The Old Mill is in Leeds.",
    facts=[{"label": "London venues", "value": "20", "source_id": "venues.csv"},
           {"label": "City", "value": "Leeds", "source_id": "venues.csv#V012"}],
    source_ids=["venues.csv", "venues.csv#V012"],
    confidence="high",
)
CHUNKS = {c.chunk_id: c for c in build_chunks(read_sources())}


def test_router_history_drops_error_turns_and_carries_the_plan():
    gala = PipelineResult(
        question="Gala dinner in Leeds?",
        answer=ANSWER.model_copy(update={"answer": "Four venues fit."}),
        plan=PLAN.model_copy(update={"standalone_question": "Which Leeds venues fit a gala dinner?"}),
        sql=SqlResult(sql="SELECT v.venue_id FROM venues AS v WHERE v.city = 'Leeds'"),
    )
    messages = [
        {"role": "user", "content": "Gala dinner in Leeds?"},
        {"role": "assistant", "content": "Four venues fit.", "result": gala},
        {"role": "user", "content": "And parking?"},
        {"role": "assistant", "content": LIMIT_TEXT, "error": True},
    ]

    history = router_history(messages)

    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert history[1]["content"] == (
        "Four venues fit.\nEarlier plan: question \"Which Leeds venues fit a gala dinner?\"; "
        "SQL: SELECT v.venue_id FROM venues AS v WHERE v.city = 'Leeds'"
    )


def test_fact_rows():
    assert fact_rows(ANSWER)[1] == {"Fact": "City", "Value": "Leeds", "Source": "venues.csv#V012"}


def test_cited_sources_show_record_text_or_a_note_for_aggregates():
    result = PipelineResult(question="How many?", answer=ANSWER, plan=PLAN)

    sources = dict(cited_sources(result, CHUNKS))

    assert sources["venues.csv#V012"].startswith("Source: venues.csv | ID: V012")
    assert "computed from venues.csv" in sources["venues.csv"]


def test_sql_rows_show_empty_values_and_lists():
    sql = SqlResult(
        sql="SELECT ...",
        columns=["venue_id", "parking_spaces", "suitable_venue_types"],
        rows=[["V045", None, ["hotel", "museum"]]],
    )
    assert sql_rows(sql) == [{"venue_id": "V045", "parking_spaces": NOT_GIVEN, "suitable_venue_types": "hotel, museum"}]


def test_column_with_an_empty_value_becomes_text():
    sql = SqlResult(sql="SELECT ...", columns=["venue_id", "parking_spaces", "seated_capacity"],
                    rows=[["V012", 20, 120], ["V045", None, 180]])
    assert sql_rows(sql) == [
        {"venue_id": "V012", "parking_spaces": "20", "seated_capacity": 120},
        {"venue_id": "V045", "parking_spaces": NOT_GIVEN, "seated_capacity": 180},
    ]


def test_hit_rows_round_the_scores():
    hit = SearchHit(
        chunk_id="venues.csv#V012", source="venues.csv", record_id="V012", score=0.0327869,
        vector_similarity=0.69812, bm25_score=None, vector_rank=1, bm25_rank=None, context_text="...",
    )
    assert hit_rows([hit]) == [{
        "Source": "venues.csv#V012", "RRF score": 0.0328, "Vector similarity": 0.698,
        "Vector rank": 1, "BM25 score": None, "BM25 rank": None,
    }]


def test_error_messages():
    request = httpx2.Request("POST", "http://test")
    assert error_message(DailyLimitReached()) == LIMIT_TEXT
    assert error_message(InvalidOutput()) == INVALID_TEXT
    assert error_message(ProviderError("empty")) == SERVICE_TEXT
    assert error_message(openai.APIConnectionError(request=request)) == SERVICE_TEXT
    assert error_message(ValueError("x")) == OTHER_TEXT
