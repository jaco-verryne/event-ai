"""Score Part 1 on the 12 evaluation questions (CLAUDE.md section 11).

    python eval/run_part1.py                # retrieval, then the full ask() flow (about 24 LLM calls)
    python eval/run_part1.py --router-only  # retrieval and the router only (12 LLM calls)
    python eval/run_part1.py --skip-router  # retrieval only, no LLM calls

Writes eval/results/<date>_part1.json.
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so that "python eval/run_part1.py" finds the eventai package

from eventai.config import load_settings  # noqa: E402
from eventai.llm import DailyLimitReached, build_providers  # noqa: E402
from eventai import tracing  # noqa: E402
from eventai.rag.pipeline import ask, load_resources  # noqa: E402
from eventai.rag.query_sql import query_sql  # noqa: E402
from eventai.rag.router import plan_question  # noqa: E402
from eventai.rag.search_text import DOCUMENTS, search_text  # noqa: E402

QUESTIONS = ROOT / "eval" / "part1_questions.yaml"
RESULTS = ROOT / "eval" / "results"
ALL_DOCUMENTS = sorted(set(DOCUMENTS.values()))
K = 5
# The Groq free plan allows 8,000 tokens a minute; one router call uses about a third.
RATE_LIMIT_WAIT_SECONDS = 65
RATE_LIMIT_ATTEMPTS = 3
QUESTION_PAUSE_SECONDS = 30  # one full question uses about half of the tokens a minute


def tool_sets(q: dict) -> list[set[str]]:
    return [set(q["expected_tools"]), *(set(t) for t in q.get("accepted_tools", []))]


def run_sql(con, sql: str) -> tuple[list[str], list[tuple]]:
    cursor = con.execute(sql)
    return [d[0] for d in cursor.description], cursor.fetchall()


def ids_in(columns: list[str], rows: list[tuple]) -> set[str]:
    id_columns = [i for i, name in enumerate(columns) if name.endswith("_id")]
    return {row[i] for row in rows for i in id_columns if row[i] is not None}


def sql_matches(q: dict, result: tuple, reference: tuple) -> bool:
    """Compare result rows, not SQL text: different SQL can be correct (page 2, D9)."""
    expected = set(q["expected_record_ids"])
    if not expected:  # aggregate or empty result: compare the cell values
        cells = lambda rows: Counter(str(v) for row in rows for v in row)  # noqa: E731
        return cells(result[1]) == cells(reference[1])
    found = ids_in(*result)
    mixed = set(q["expected_tools"]) == {"query_sql", "search_text"}
    # A mixed question needs every candidate row; search_text then ranks them.
    return expected <= found if mixed else found == expected


def score_retrieval(index, con, questions: list[dict]) -> dict:
    rows = []
    for q in questions:
        if not any("search_text" in tools for tools in tool_sets(q)):
            continue
        record_ids = None
        if "query_sql" in q["expected_tools"]:
            # As in the pipeline: the SQL selects the rows, then search_text ranks them.
            record_ids = sorted(ids_in(*run_sql(con, q["reference_sql"])))
        hits = search_text(index, q["question"], ALL_DOCUMENTS, record_ids, k=K)
        found = [h.record_id for h in hits]
        expected = set(q["expected_record_ids"])
        rows.append({
            "id": q["id"],
            "hit": bool(expected & set(found)),
            "recall": round(len(expected & set(found)) / min(len(expected), K), 2),
            "sql_prefilter": record_ids is not None,
            "top": [
                {"record_id": h.record_id, "vector_similarity": round(h.vector_similarity or 0, 3),
                 "bm25_rank": h.bm25_rank, "rrf": round(h.score, 4)}
                for h in hits
            ],
        })
    return {
        "k": K,
        "hit_rate": round(sum(r["hit"] for r in rows) / len(rows), 2),
        "mean_recall": round(sum(r["recall"] for r in rows) / len(rows), 2),
        "questions": rows,
    }


def score_router(con, schema: str, questions: list[dict]) -> dict:
    # Primary provider only: a fallback would mix two models in one score.
    providers = build_providers(load_settings())[:1]
    by_id = {q["id"]: q for q in questions}
    rows = []
    for q in questions:
        history = []
        if "follow_up_of" in q:
            earlier = by_id[q["follow_up_of"]]
            # Stand-in answer until the answer step exists (Fri: the real answer).
            history = [
                {"role": "user", "content": earlier["question"]},
                {"role": "assistant", "content": "Answer: " + ", ".join(earlier["expected_facts"])},
            ]
        row = {"id": q["id"], "question": q["question"]}
        try:
            plan = _plan_with_pacing(q["question"], history, schema, providers)
        except Exception as err:  # a failed call is a failed score, not a crash
            rows.append({**row, "error": f"{type(err).__name__}: {err}", "tool_ok": False, "sql_ok": None})
            continue
        row.update(plan=plan.model_dump(), tool_ok=set(plan.tools) in tool_sets(q), sql_ok=None)
        if plan.sql and "reference_sql" in q:
            # All the guardrails, but no repair: the score measures the router's own SQL.
            result = query_sql(con, plan.sql)
            if result.error:
                row.update(sql_ok=False, sql_error=result.error)
            else:
                row["sql_ok"] = sql_matches(q, (result.columns, result.rows), run_sql(con, q["reference_sql"]))
                row["sql_record_ids"] = sorted(ids_in(result.columns, result.rows))
        rows.append(row)
    checked = [r for r in rows if r["sql_ok"] is not None]
    return {
        "model": f"{providers[0].name}: {providers[0].model}",
        "tool_choice": round(sum(r["tool_ok"] for r in rows) / len(rows), 2),
        "sql_result": round(sum(r["sql_ok"] for r in checked) / len(checked), 2) if checked else None,
        "sql_checked": len(checked),
        "questions": rows,
    }


def normalise(text: str) -> str:
    """For the fact check: case, "£", thousands commas and non-breaking hyphens do not count."""
    return text.lower().replace("£", "").replace(",", "").replace("‑", "-")


def score_answers(resources, questions: list[dict]) -> dict:
    """The full flow, as a user sees it: tools, SQL (with repair), answer and citation check."""
    providers = build_providers(load_settings())[:1]  # one model for the whole score
    by_id = {q["id"]: q for q in questions}
    answers: dict[int, str] = {}
    rows = []
    for n, q in enumerate(questions):
        if n:
            time.sleep(QUESTION_PAUSE_SECONDS)
        history = []
        if "follow_up_of" in q:
            earlier = q["follow_up_of"]
            history = [
                {"role": "user", "content": by_id[earlier]["question"]},
                {"role": "assistant", "content": answers.get(earlier, "")},
            ]
        row = {"id": q["id"], "question": q["question"]}
        try:
            result = _ask_with_pacing(q["question"], history, resources, providers)
        except Exception as err:  # a failed call is a failed score, not a crash
            rows.append({**row, "error": f"{type(err).__name__}: {err}", "tool_ok": False, "sql_ok": None,
                         "accuracy": 0.0, "facts": 0, "removed": 0, "cites_expected": None})
            continue
        answers[q["id"]] = result.answer.answer

        sql_ok = None
        if result.sql is not None and "reference_sql" in q:
            sql = result.sql
            reference = run_sql(resources.con, q["reference_sql"])
            sql_ok = sql.error is None and sql_matches(q, (sql.columns, sql.rows), reference)
        text = normalise(" ".join([result.answer.answer, *(f.value for f in result.answer.facts)]))
        found = [f for f in q["expected_facts"] if normalise(f) in text]
        cited = {s.split("#", 1)[1] for s in result.answer.source_ids if "#" in s}
        expected_ids = set(q["expected_record_ids"])
        rows.append({
            **row,
            "tools": result.plan.tools,
            "tool_ok": set(result.plan.tools) in tool_sets(q),
            "sql": result.sql.sql if result.sql else None,
            "sql_ok": sql_ok,
            "sql_repaired": bool(result.sql and result.sql.repaired),
            "answer": result.answer.answer,
            "confidence": result.answer.confidence,
            "facts": len(result.answer.facts) + len(result.removed_facts),
            "removed": len(result.removed_facts),
            "source_ids": result.answer.source_ids,
            "expected_facts_found": found,
            "accuracy": round(len(found) / len(q["expected_facts"]), 2),
            "cites_expected": bool(cited & expected_ids) if expected_ids else None,
            "trace_id": result.trace_id,
        })

    checked = [r for r in rows if r["sql_ok"] is not None]
    cite_checked = [r for r in rows if r["cites_expected"] is not None]
    facts = sum(r["facts"] for r in rows)
    return {
        "model": f"{providers[0].name}: {providers[0].model}",
        "tool_choice": round(sum(r["tool_ok"] for r in rows) / len(rows), 2),
        "sql_result": round(sum(r["sql_ok"] for r in checked) / len(checked), 2) if checked else None,
        "sql_checked": len(checked),
        "sql_repairs": sum(r.get("sql_repaired", False) for r in rows),
        "answer_accuracy": round(sum(r["accuracy"] for r in rows) / len(rows), 2),
        "answers_fully_correct": sum(r["accuracy"] == 1.0 for r in rows),
        "facts_cited": facts,
        "facts_removed": sum(r["removed"] for r in rows),
        "answers_with_removed_facts": sum(r["removed"] > 0 for r in rows),
        "cites_expected_record": round(sum(r["cites_expected"] for r in cite_checked) / len(cite_checked), 2),
        "questions": rows,
    }


def _ask_with_pacing(question: str, history: list[dict], resources, providers):
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        try:
            return ask(question, history, resources, providers=providers, session_id=f"eval-{date.today()}")
        except DailyLimitReached:
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise
            print(f"  rate limit: waiting {RATE_LIMIT_WAIT_SECONDS} s", flush=True)
            time.sleep(RATE_LIMIT_WAIT_SECONDS)


def _plan_with_pacing(question: str, history: list[dict], schema: str, providers):
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        try:
            return plan_question(question, history, schema=schema, providers=providers)
        except DailyLimitReached:
            if attempt == RATE_LIMIT_ATTEMPTS:
                raise
            print(f"  rate limit: waiting {RATE_LIMIT_WAIT_SECONDS} s", flush=True)
            time.sleep(RATE_LIMIT_WAIT_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="  %(message)s")
    logging.getLogger("eventai.llm").setLevel(logging.INFO)  # shows the tokens per call
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--skip-router", action="store_true", help="retrieval only, no LLM calls")
    parser.add_argument("--router-only", action="store_true", help="retrieval and the router only")
    args = parser.parse_args()

    tracing.init_tracing(environment="eval")  # eval traces stay apart from app traces
    questions = yaml.safe_load(QUESTIONS.read_text())
    resources = load_resources()

    report = {"date": date.today().isoformat(), "retrieval": score_retrieval(resources.index, resources.con, questions)}
    if args.router_only:
        report["router"] = score_router(resources.con, resources.schema, questions)
    elif not args.skip_router:
        report["answers"] = score_answers(resources, questions)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{report['date']}_part1.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")

    r = report["retrieval"]
    print(f"Retrieval hit@{K}: {r['hit_rate']:.0%}   mean recall@{K}: {r['mean_recall']:.0%}")
    for row in r["questions"]:
        top = ", ".join(t["record_id"] for t in row["top"])
        print(f"  Q{row['id']:<3} hit={row['hit']!s:5} recall={row['recall']:.2f}  top: {top}")
    if "router" in report:
        rt = report["router"]
        sql = f"{rt['sql_result']:.0%} of {rt['sql_checked']}" if rt["sql_result"] is not None else "n/a"
        print(f"Router tool choice: {rt['tool_choice']:.0%}   SQL result check: {sql}")
        for row in rt["questions"]:
            tools = ",".join(row["plan"]["tools"]) if "plan" in row else row.get("error", "")
            print(f"  Q{row['id']:<3} tools_ok={row['tool_ok']!s:5} sql_ok={row['sql_ok']!s:5} {tools}")
    if "answers" in report:
        a = report["answers"]
        sql = f"{a['sql_result']:.0%} of {a['sql_checked']}" if a["sql_result"] is not None else "n/a"
        print(
            f"Full flow ({a['model']}): tool choice {a['tool_choice']:.0%}, SQL result {sql} "
            f"({a['sql_repairs']} repaired), answer accuracy {a['answer_accuracy']:.0%} "
            f"({a['answers_fully_correct']} of {len(a['questions'])} fully correct), "
            f"facts removed {a['facts_removed']} of {a['facts_cited']}, "
            f"cites an expected record {a['cites_expected_record']:.0%}"
        )
        for row in a["questions"]:
            detail = row.get("error") or row["answer"][:90]
            print(f"  Q{row['id']:<3} tools_ok={row['tool_ok']!s:5} sql_ok={row['sql_ok']!s:5} "
                  f"acc={row['accuracy']:.2f} removed={row['removed']}  {detail}")
    print(f"Wrote {out.relative_to(ROOT)}")
    tracing.flush()


if __name__ == "__main__":
    main()
