"""Pure helpers for the Streamlit chat. They turn a PipelineResult into rows and text, so the app
file stays thin and this logic has tests."""

from collections.abc import Mapping, Sequence
from typing import Any

import openai

from eventai.llm import DailyLimitReached, InvalidOutput, ProviderError
from eventai.rag.answer import Answer
from eventai.rag.chunks import NOT_GIVEN, Chunk
from eventai.rag.pipeline import PipelineResult
from eventai.rag.query_sql import SqlResult
from eventai.rag.search_text import SearchHit

LIMIT_TEXT = "The free model limit is reached. Wait one minute, then ask again."
INVALID_TEXT = "The model gave an answer that failed the check twice. Ask the question in other words."
SERVICE_TEXT = "The model service does not answer now. Try again in a minute."
OTHER_TEXT = "Something went wrong. Try again, or ask the question in other words."


def router_history(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The earlier chat turns for the router. Error turns are not part of the conversation."""
    return [{"role": m["role"], "content": m["content"]} for m in messages if not m.get("error")]


def fact_rows(answer: Answer) -> list[dict[str, str]]:
    return [{"Fact": f.label, "Value": f.value, "Source": f.source_id} for f in answer.facts]


def cited_sources(result: PipelineResult, chunks: Mapping[str, Chunk]) -> list[tuple[str, str]]:
    """Each cited source ID with the record text. A file-level ID comes from an aggregate."""
    sources = []
    for source_id in result.answer.source_ids:
        chunk = chunks.get(source_id)
        if chunk is not None:
            sources.append((source_id, chunk.context_text))
        else:
            sources.append((source_id, f"A value that the SQL query computed from {source_id}. "
                                       "The Debug panel shows the SQL and the rows."))
    return sources


def sql_rows(sql: SqlResult) -> list[dict[str, Any]]:
    return [{c: _cell(v) for c, v in zip(sql.columns, row)} for row in sql.rows]


def hit_rows(hits: Sequence[SearchHit]) -> list[dict[str, Any]]:
    return [
        {
            "Source": h.chunk_id,
            "RRF score": round(h.score, 4),
            "Vector similarity": None if h.vector_similarity is None else round(h.vector_similarity, 3),
            "Vector rank": h.vector_rank,
            "BM25 score": None if h.bm25_score is None else round(h.bm25_score, 2),
            "BM25 rank": h.bm25_rank,
        }
        for h in hits
    ]


def error_message(err: Exception) -> str:
    """A plain message for the chat. The app keeps running after each of these errors."""
    if isinstance(err, DailyLimitReached):
        return LIMIT_TEXT
    if isinstance(err, InvalidOutput):
        return INVALID_TEXT
    if isinstance(err, (ProviderError, openai.APIError)):
        return SERVICE_TEXT
    return OTHER_TEXT


def _cell(value: Any) -> Any:
    if value is None:
        return NOT_GIVEN
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return value
