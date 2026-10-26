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
from eventai.tracing import current_trace_id, observation, session


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
    session_id: str | None = None,
) -> PipelineResult:
    """One question: a Langfuse trace with one observation per step (D10). `session_id` groups
    the traces of one chat."""
    history = list(history or [])
    trace_input = {"question": question, "history_turns": len(history)}
    with observation("part1.ask", input=trace_input) as root, session(session_id):
        result = _ask(question, history, resources, providers)
        result.trace_id = current_trace_id()
        root.update(output=result.answer.model_dump())
    return result


def _ask(question, history, resources, providers) -> PipelineResult:
    with observation("router", as_type="chain", input=question) as obs:
        plan = plan_question(question, history, schema=resources.schema, providers=providers)
        obs.update(output=plan.model_dump())
    result = PipelineResult(question=question, answer=fixed_answer(OUT_OF_SCOPE_TEXT, "high"), plan=plan)
    if plan.intent == "out_of_scope" or not plan.tools:
        return result

    if "query_sql" in plan.tools:

        def repair(bad_sql: str, error: str) -> str:
            return repair_sql(plan.standalone_question, bad_sql, error, schema=resources.schema, providers=providers)

        with observation("query_sql", as_type="tool", input=plan.sql) as obs:
            result.sql = query_sql(resources.con, plan.sql, repair)
            obs.update(output=result.sql.model_dump(include={
                "sql", "columns", "truncated", "record_ids", "repaired", "first_error", "error",
            }) | {"row_count": len(result.sql.rows)})

    searched = "search_text" in plan.tools
    if searched:
        record_ids = _search_filter(result.sql)
        with observation("search_text", as_type="retriever", input={
            "query": plan.search_text, "documents": plan.documents,
            "record_ids": None if record_ids is None else len(record_ids),
        }) as obs:
            result.hits = search_text(resources.index, plan.search_text, plan.documents, record_ids)
            obs.update(output=[h.model_dump(exclude={"context_text"}) for h in result.hits])

    if result.sql is not None and result.sql.error and not result.hits:
        result.answer = fixed_answer(SQL_FAILED_TEXT, "low")
        return result

    with observation("answer", as_type="chain", input=plan.standalone_question) as obs:
        answer = answer_question(plan.standalone_question, result.sql, result.hits, searched, providers)
        obs.update(output=answer.model_dump())
    allowed = allowed_source_ids(result.sql, result.hits)
    with observation("citation_check", as_type="guardrail", input={"facts": len(answer.facts), "allowed": allowed}) as obs:
        result.answer, result.removed_facts = check_citations(answer, allowed)
        obs.update(output={"removed": [f.model_dump() for f in result.removed_facts]})
    return result


def history_text(result: PipelineResult) -> str:
    """The assistant turn for the chat history: the answer plus the plan behind it. With the
    earlier SQL in view, the router can reuse its filters and joins for a follow-up (Q10)."""
    plan = [f'question "{result.plan.standalone_question}"']
    if result.sql is not None and not result.sql.error:
        plan.append(f"SQL: {result.sql.sql}")
    if result.plan.search_text:
        plan.append(f'search: "{result.plan.search_text}"')
    return f"{result.answer.answer}\nEarlier plan: " + "; ".join(plan)


def _search_filter(sql: SqlResult | None) -> list[str] | None:
    """For a mixed question, search only the rows that the SQL selected."""
    if sql is None or sql.error:
        return None
    if sql.record_ids:
        return sql.record_ids
    # No rows: nothing to rank. Rows without an ID column: no filter is possible.
    return [] if not sql.rows else None
