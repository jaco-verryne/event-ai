"""query_sql: run LLM-written SQL on DuckDB behind the six guardrails of CLAUDE.md section 8 (D9)."""

import threading
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
import sqlglot
from pydantic import BaseModel
from sqlglot import exp

from eventai.rag.loaders import TABLES

MAX_ROWS = 200
TIMEOUT_SECONDS = 5.0

ID_SOURCES = {"venue_id": "venues.csv", "package_id": "packages.json", "policy_id": "policies.csv"}
TABLE_SOURCES = {
    "venues": "venues.csv",
    "packages": "packages.json",
    "package_items": "packages.json",
    "policies": "policies.csv",
}
TABLE_ID_COLUMNS = {
    "venues": "venue_id",
    "packages": "package_id",
    "package_items": "package_id",
    "policies": "policy_id",
}
_KNOWN_COLUMNS = {c.lower() for columns in TABLES.values() for c in columns}
# Statement nodes that change data, settings or files. A SELECT root cannot hold them in
# DuckDB, but the walk costs nothing and stops a parser surprise.
_FORBIDDEN = (
    exp.DML, exp.DDL, exp.Copy, exp.Command, exp.Pragma, exp.Set, exp.Attach, exp.Detach,
    exp.Install, exp.Use, exp.Transaction, exp.Commit, exp.Rollback, exp.Export, exp.LoadData,
)


class SqlRejected(ValueError):
    """The SQL broke guardrail 2 or 3. The message goes to the LLM for the repair."""


class SqlTimeout(RuntimeError):
    """Guardrail 5 stopped the query."""


class SqlResult(BaseModel):
    sql: str  # the SQL that ran, or the last SQL that failed
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False
    record_ids: list[str] = []  # bare IDs, for the search_text filter
    source_ids: list[str] = []  # citations: "venues.csv#V012", or "venues.csv" for an aggregate
    repaired: bool = False
    first_error: str | None = None
    error: str | None = None  # set when the query failed twice: the answer says it cannot answer
    added_id_columns: list[str] = []  # ID columns that code added, so that each row can be cited


def check_sql(sql: str) -> exp.Expression:
    """Guardrails 2 and 3. Returns the checked tree."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as err:
        raise SqlRejected(f"The SQL does not parse: {err}") from err
    if len(statements) != 1:
        raise SqlRejected(f"Write exactly one statement, not {len(statements)}.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise SqlRejected(f"Only a SELECT statement is allowed, not {type(tree).__name__.upper()}.")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            raise SqlRejected(f"{type(node).__name__.upper()} is not allowed inside the query.")

    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlRejected(f"Table functions are not allowed: {table.this.sql(dialect='duckdb')}.")
        if table.args.get("db") or table.args.get("catalog"):
            raise SqlRejected(f"Use the table name only, without a schema: {table.sql(dialect='duckdb')}.")
        name = table.name.lower()
        if name not in TABLES and name not in ctes:
            raise SqlRejected(f"Unknown table '{table.name}'. Use only: {', '.join(TABLES)}.")

    defined = {a.alias.lower() for a in tree.find_all(exp.Alias)}
    for alias in tree.find_all(exp.TableAlias):
        defined.add(alias.name.lower())
        defined.update(c.name.lower() for c in alias.columns)
    for column in tree.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        name = column.name.lower()
        if name not in _KNOWN_COLUMNS and name not in defined:
            raise SqlRejected(f"Unknown column '{column.name}'.")
    return tree


def add_id_columns(tree: exp.Expression) -> tuple[exp.Expression, list[str]]:
    """Add the ID column of each table to a plain SELECT, so that each row can be cited.

    The router prompt asks for the IDs (SQL rule 2), but the model sometimes leaves one out
    (Q9: p.package_id). A query with GROUP BY, DISTINCT or an aggregate stays as it is,
    because an extra column would change its rows."""
    if not isinstance(tree, exp.Select) or tree.args.get("distinct") or tree.args.get("group"):
        return tree, []
    projections = tree.expressions
    if any(isinstance(e, exp.Star) or e.find(exp.AggFunc) for e in projections):
        return tree, []
    present = {e.alias_or_name.lower() for e in projections}
    starred = {e.table.lower() for e in projections if isinstance(e, exp.Column) and isinstance(e.this, exp.Star)}

    tables = [tree.args["from_"].this] if tree.args.get("from_") else []
    tables += [join.this for join in tree.args.get("joins") or []]
    added = []
    for table in tables:
        if not isinstance(table, exp.Table):  # a subquery
            continue
        id_column = TABLE_ID_COLUMNS.get(table.name.lower())
        qualifier = table.alias_or_name
        if id_column is None or id_column in present or qualifier.lower() in starred:
            continue
        tree = tree.select(exp.column(id_column, table=qualifier), append=True)
        present.add(id_column)
        added.append(f"{qualifier}.{id_column}")
    return tree, added


def run_with_timeout(
    con: duckdb.DuckDBPyConnection, sql: str, seconds: float = TIMEOUT_SECONDS
) -> tuple[list[str], list[tuple]]:
    """Guardrail 5: a worker thread runs the query; the caller interrupts it after `seconds`."""
    cursor = con.cursor()  # one cursor per query, so parallel app sessions do not share state
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            cursor.execute(sql)
            outcome["columns"] = [d[0] for d in cursor.description]
            outcome["rows"] = cursor.fetchall()
        except Exception as err:  # re-raised in the caller's thread
            outcome["error"] = err

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(seconds)
    try:
        if worker.is_alive():
            cursor.interrupt()
            worker.join(1.0)
            raise SqlTimeout(f"The query ran for more than {seconds:g} s, so it was stopped.")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["columns"], outcome["rows"]
    finally:
        if not worker.is_alive():
            cursor.close()


def query_sql(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    repair: Callable[[str, str], str] | None = None,
) -> SqlResult:
    """Run the SQL behind all the guardrails. On an error, `repair(sql, error)` gets one try
    (guardrail 6). Guardrail 1 is the read-only connection from loaders.connect_readonly()."""
    try:
        return _run(con, sql)
    except (SqlRejected, SqlTimeout, duckdb.Error) as err:
        first_error = str(err)
    if repair is None:
        return SqlResult(sql=sql, error=first_error, first_error=first_error)

    repaired_sql = repair(sql, first_error)
    try:
        result = _run(con, repaired_sql)
    except (SqlRejected, SqlTimeout, duckdb.Error) as err:
        return SqlResult(sql=repaired_sql, repaired=True, first_error=first_error, error=str(err))
    return result.model_copy(update={"repaired": True, "first_error": first_error})


def _run(con: duckdb.DuckDBPyConnection, sql: str) -> SqlResult:
    tree, added_id_columns = add_id_columns(check_sql(sql))
    # Run the SQL that sqlglot generates from the checked tree: what runs is what was checked.
    checked = tree.sql(dialect="duckdb", comments=False)
    # Guardrail 4: one extra row tells us that the result was cut.
    limited = f"SELECT * FROM ({checked}) AS limited LIMIT {MAX_ROWS + 1}"
    columns, rows = run_with_timeout(con, limited)
    truncated = len(rows) > MAX_ROWS
    rows = [[_json_safe(v) for v in row] for row in rows[:MAX_ROWS]]

    record_ids, source_ids = [], []
    for i, column in enumerate(columns):
        source = ID_SOURCES.get(column.lower())
        if source is None:
            continue
        for row in rows:
            if row[i] is not None and row[i] not in record_ids:
                record_ids.append(row[i])
                source_ids.append(f"{source}#{row[i]}")
    if not source_ids:
        # An aggregate or an empty result: cite the documents that the query read.
        tables = {t.name.lower() for t in tree.find_all(exp.Table)}
        source_ids = sorted({TABLE_SOURCES[t] for t in tables if t in TABLE_SOURCES})
    return SqlResult(
        sql=checked,
        columns=columns,
        rows=rows,
        truncated=truncated,
        record_ids=record_ids,
        source_ids=source_ids,
        added_id_columns=added_id_columns,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return list(value)
    return value
