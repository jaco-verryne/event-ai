"""ask(): the Part 1 flow. Router -> query_sql and/or search_text -> answer -> citation check."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import duckdb
from pydantic import BaseModel

from eventai.llm import Provider
from eventai.rag.answer import (
    OUT_OF_SCOPE_TEXT,
    SQL_FAILED_TEXT,
    Answer,
    Fact,
    allowed_source_ids,
    answer_question,
    check_citations,
    fixed_answer,
)
from eventai.rag.loaders import DATA_DIR, DB_PATH, build_chunks, build_database, connect_readonly, read_sources
from eventai.rag.query_sql import SqlResult, query_sql
from eventai.rag.router import RouterPlan, plan_question, repair_sql, schema_text
from eventai.rag.search_text import Embedder, SearchHit, TextIndex, build_text_index, search_text


@dataclass(frozen=True)
class Resources:
    """Built once at start-up; the UI caches it with st.cache_resource."""

    con: duckdb.DuckDBPyConnection
    index: TextIndex
    schema: str


class PipelineResult(BaseModel):
    """The answer plus what the debug panel shows."""

    question: str
    answer: Answer
    plan: RouterPlan
    sql: SqlResult | None = None
    hits: list[SearchHit] = []
    removed_facts: list[Fact] = []
    trace_id: str | None = None


def load_resources(
    data_dir: Path = DATA_DIR, db_path: Path = DB_PATH, embedder: Embedder | None = None
) -> Resources:
    sources = read_sources(data_dir)
    con = connect_readonly(build_database(sources, db_path))
    return Resources(con, build_text_index(build_chunks(sources), embedder), schema_text(sources))


def ask(
    question: str,
    history: Sequence[dict[str, str]] | None,
    resources: Resources,
    providers: Sequence[Provider] | None = None,
) -> PipelineResult:
    plan = plan_question(question, history, schema=resources.schema, providers=providers)
    result = PipelineResult(question=question, answer=fixed_answer(OUT_OF_SCOPE_TEXT, "high"), plan=plan)
    if plan.intent == "out_of_scope" or not plan.tools:
        return result

    if "query_sql" in plan.tools:

        def repair(bad_sql: str, error: str) -> str:
            return repair_sql(plan.standalone_question, bad_sql, error, schema=resources.schema, providers=providers)

        result.sql = query_sql(resources.con, plan.sql, repair)

    searched = "search_text" in plan.tools
    if searched:
        result.hits = search_text(resources.index, plan.search_text, plan.documents, _search_filter(result.sql))

    if result.sql is not None and result.sql.error and not result.hits:
        result.answer = fixed_answer(SQL_FAILED_TEXT, "low")
        return result

    answer = answer_question(plan.standalone_question, result.sql, result.hits, searched, providers)
    result.answer, result.removed_facts = check_citations(answer, allowed_source_ids(result.sql, result.hits))
    return result


def _search_filter(sql: SqlResult | None) -> list[str] | None:
    """For a mixed question, search only the rows that the SQL selected."""
    if sql is None or sql.error:
        return None
    if sql.record_ids:
        return sql.record_ids
    # No rows: nothing to rank. Rows without an ID column: no filter is possible.
    return [] if not sql.rows else None
