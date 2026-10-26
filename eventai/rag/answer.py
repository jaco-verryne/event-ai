"""The answer step: one LLM call that uses only the tool results, then a citation check in code."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from eventai.llm import Provider, complete_json
from eventai.rag.chunks import NOT_GIVEN
from eventai.rag.query_sql import ID_SOURCES, SqlResult
from eventai.rag.search_text import SearchHit

OUT_OF_SCOPE_TEXT = "I can only answer questions about our partner venues, event packages and booking terms."
SQL_FAILED_TEXT = "I cannot answer this question from the data, because the database query failed twice."
VAT_NOTE = "Prices exclude VAT."


class Fact(BaseModel):
    label: str
    value: str
    source_id: str  # "venues.csv#V012"


class Answer(BaseModel):
    answer: str
    facts: list[Fact]
    source_ids: list[str]
    confidence: Literal["high", "medium", "low"]


ANSWER_PROMPT = """\
You answer questions from the sales planners of a UK event company. Use only the tool results in \
the user message. Do not use other knowledge.

Rules:
1. Each fact cites exactly one source_id from the list "Allowed source IDs". Do not make up an ID.
2. source_ids lists each source ID that supports the answer.
3. When a value shows "not given in the data", write "The data does not give" the value for that \
record. Do not guess the value.
4. When the answer gives prices, say that the prices exclude VAT.
5. For rules with ranges (for example days before the event), pick the one rule whose condition \
includes the value in the question, and say why it matches.
6. When a rule applies to one package only, use it for that package, and say that it replaces the \
general rule.
7. When the query returned no rows, say that the data has no records that match, and name the filter \
(for example the city).
8. When the tool results do not answer the question, say that the data does not have the answer.
9. answer: two to four short sentences in plain English. facts: the key values, one value per fact.
10. confidence: "high" when the results answer the question directly; "medium" when you combine \
records or interpret a rule; "low" when the data does not answer the question.
"""


def fixed_answer(text: str, confidence: Literal["high", "medium", "low"]) -> Answer:
    """An answer that needs no LLM call."""
    return Answer(answer=text, facts=[], source_ids=[], confidence=confidence)


def allowed_source_ids(sql: SqlResult | None, hits: Sequence[SearchHit]) -> list[str]:
    ids = list(sql.source_ids) if sql and not sql.error else []
    ids += [h.chunk_id for h in hits]
    return list(dict.fromkeys(ids))


def tool_context(sql: SqlResult | None, hits: Sequence[SearchHit], searched: bool = False) -> str:
    """The tool results as text for the prompt. Each row and each hit shows its source IDs."""
    parts = []
    if sql is not None:
        lines = ["Database query (query_sql):", f"SQL: {sql.sql}"]
        if sql.error:
            lines.append(f"The query failed twice: {sql.error}")
        elif not sql.rows:
            lines.append("The query returned no rows.")
        else:
            for row in sql.rows:
                lines.append(f"[{', '.join(_row_sources(sql, row))}] " + " | ".join(
                    f"{c}: {NOT_GIVEN if v is None else v}" for c, v in zip(sql.columns, row)
                ))
            if sql.truncated:
                lines.append(f"The result has more rows; only the first {len(sql.rows)} are shown.")
        parts.append("\n".join(lines))
    if hits:
        lines = ["Text search (search_text):"]
        for h in hits:
            lines.append(f"[{h.chunk_id}]\n{h.context_text}")
        parts.append("\n\n".join(lines))
    elif searched:
        parts.append("Text search (search_text): no text matched above the minimum score.")
    return "\n\n".join(parts)


def answer_question(
    question: str,
    sql: SqlResult | None,
    hits: Sequence[SearchHit],
    searched: bool = False,
    providers: Sequence[Provider] | None = None,
) -> Answer:
    allowed = allowed_source_ids(sql, hits)
    user = (
        f"Question: {question}\n\n{tool_context(sql, hits, searched)}\n\n"
        f"Allowed source IDs: {', '.join(allowed) if allowed else 'none'}"
    )
    messages = [{"role": "system", "content": ANSWER_PROMPT}, {"role": "user", "content": user}]
    return complete_json(messages, Answer, providers)


def check_citations(answer: Answer, allowed: Sequence[str]) -> tuple[Answer, list[Fact]]:
    """Keep only the facts whose source ID was in the tool results (CLAUDE.md section 7.4)."""
    allowed_set = set(allowed)
    kept = [f for f in answer.facts if f.source_id in allowed_set]
    removed = [f for f in answer.facts if f.source_id not in allowed_set]
    source_ids = [s for s in dict.fromkeys(answer.source_ids) if s in allowed_set]
    source_ids += [f.source_id for f in kept if f.source_id not in source_ids]

    confidence = answer.confidence
    if answer.facts and not kept:
        confidence = "low"
    text = answer.answer
    # A code check, because the prompt rule alone can be missed.
    if _mentions_price(text, kept) and "vat" not in text.lower():
        text = f"{text.rstrip()} {VAT_NOTE}"
    checked = answer.model_copy(
        update={"answer": text, "facts": kept, "source_ids": source_ids, "confidence": confidence}
    )
    return checked, removed


def _row_sources(sql: SqlResult, row: list) -> list[str]:
    ids = [
        f"{ID_SOURCES[c.lower()]}#{v}"
        for c, v in zip(sql.columns, row)
        if c.lower() in ID_SOURCES and v is not None
    ]
    # A row with no ID column (an aggregate) is cited by the documents that the query read.
    return ids or [s for s in sql.source_ids if "#" not in s]


def _mentions_price(text: str, facts: Sequence[Fact]) -> bool:
    return "£" in text or any("£" in f.value for f in facts)
