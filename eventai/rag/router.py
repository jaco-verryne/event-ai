"""The router: one LLM call turns a question into a plan with the tools, the SQL and the search words."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, model_validator

from eventai.llm import Provider, complete_json
from eventai.rag.loaders import TABLES, Sources

HISTORY_TURNS = 6

TABLE_NOTES = {
    "venues": "one row per partner venue (venues.csv)",
    "packages": "one row per event package (packages.json)",
    "package_items": "the included items and the add-ons of each package (packages.json)",
    "policies": "one row per booking rule (policies.csv)",
}
COLUMN_NOTES = {
    "venues": {
        "venue_id": "ID, for example 'V012'",
        "name": "venue name",
        "city": "city",
        "venue_type": "type of venue",
        "description": "one sentence on the style and the features (text: search_text finds meaning here)",
        "seated_capacity": "maximum number of seated guests",
        "standing_capacity": "maximum number of standing guests",
        "day_rate_gbp": "venue hire for one day, in GBP, without VAT",
        "step_free_access": "true when the venue has step-free access",
        "parking_spaces": "number of parking spaces; NULL when the data does not give the value",
        "av_included": "true when audio-visual equipment is included",
        "catering": "who supplies the food",
        "nearest_station": "nearest railway station",
        "walk_minutes": "walk from the nearest station, in minutes",
    },
    "packages": {
        "package_id": "ID, for example 'PKG-05'",
        "name": "package name",
        "event_type": "type of event",
        "description": "two or three sentences on the package (text: search_text finds meaning here)",
        "min_guests": "minimum number of guests",
        "max_guests": "maximum number of guests",
        "price_per_head_gbp": "price per guest, in GBP, without VAT",
        "lead_time_weeks": "minimum weeks between the booking and the event",
        "suitable_venue_types": "list of venue_type values that suit the package",
    },
    "package_items": {
        "package_id": "the package of the item (packages.package_id)",
        "kind": "'include' for an item in the package price, 'add_on' for an extra at a cost",
        "name": "item name",
        "price_gbp": "add-on price in GBP, without VAT; NULL for included items",
    },
    "policies": {
        "policy_id": "ID, for example 'POL-CAN-02'",
        "area": "policy area",
        "applies_to": "'all' for all packages, or one package_id",
        "condition": "when the rule applies, as text (for example a range of days)",
        "rule": "what the rule says, as text",
        "effective_from": "date from which the rule applies",
    },
}
# Columns where the prompt lists every value in the data, so the SQL uses exact values.
CATEGORY_COLUMNS = {
    "venues": ["city", "venue_type", "catering"],
    "packages": ["event_type"],
    "policies": ["area", "applies_to"],
}

SQL_RULES = """\
SQL rules:
1. Write one SELECT statement for DuckDB. Use only the tables and the columns below.
2. Always select the ID column of each table in the FROM and JOIN clauses (venue_id, package_id, \
policy_id), so that the answer can cite each row and each value. For a join of venues and packages, \
select both v.venue_id and p.package_id.
3. For a policy question, select all the rules of the policy area, for example \
WHERE area = 'cancellation'. Do not filter on the number of days or the amount in the question. \
The answer step picks the correct rule.
4. When the question asks about a value that can be NULL (for example parking_spaces), select the \
column and keep every row. Do not filter on that column (no IS NOT NULL, no > 0): the answer step \
must see the rows where the data does not give the value.
5. To match packages to venues, use list_contains(p.suitable_venue_types, v.venue_type).
6. Use the exact values from the lists below. When a city or a value is not in a list, still query \
for it, so that the result shows that the data has no rows.
7. Prices exclude VAT. Do not add VAT.
8. Do not use table functions (for example read_csv or range) or file paths. Use no schema prefix."""

_ROUTER_TEMPLATE = """\
You plan how to answer a question from the sales planners of a UK event company. \
The data has three documents in four DuckDB tables. Do not answer the question. Return one JSON plan.

Tools:
- query_sql: one DuckDB SELECT statement on the tables below. Use it for numbers, categories, IDs, \
counts, minimum and maximum values, and filters on attributes (city, capacity, price, access, parking, \
dates). Use it for each policy question.
- search_text: a meaning search on the text fields (venue name, type and description; package name, \
description, included items and add-ons; policy condition and rule). Use it for style, features, \
atmosphere and suitability, for example "rustic", "space to enjoy a summer evening" or "suits a team event".
- Use both tools when the question has a filter part and a meaning part. The SQL selects the candidate \
rows. Then search_text ranks those rows by meaning.

{sql_rules}

Other fields:
- intent: lookup (one record), list (the records that match filters), aggregate (count, minimum, \
maximum, average), policy (booking terms), compare (two or more records), out_of_scope (not about \
venues, packages or booking terms).
- documents: the documents that the tools use: packages, venues, policies.
- standalone_question: the question, complete without the chat history. For a follow-up question \
(for example "those venues"), repeat the filters of the earlier question in the SQL and in the \
standalone question. An assistant turn ends with "Earlier plan:", the question and the SQL that \
answered it. Reuse all its filters and joins, then add the new condition.
- For out_of_scope, tools and documents are empty lists, and sql and search_text are null.

Schema:
{schema}

Examples:
Question: Which hotels in Bristol include AV equipment?
{"intent": "list", "tools": ["query_sql"], "documents": ["venues"], "sql": "SELECT venue_id, name FROM venues WHERE city = 'Bristol' AND venue_type = 'hotel' AND av_included", "search_text": null, "standalone_question": "Which hotels in Bristol include AV equipment?"}

Question: Which venue has a vaulted ceiling?
{"intent": "lookup", "tools": ["search_text"], "documents": ["venues"], "sql": null, "search_text": "vaulted ceiling", "standalone_question": "Which venue has a vaulted ceiling?"}

Question: Find a rooftop bar in Glasgow with a relaxed feel for 60 seated guests.
{"intent": "list", "tools": ["query_sql", "search_text"], "documents": ["venues"], "sql": "SELECT venue_id, name, seated_capacity FROM venues WHERE city = 'Glasgow' AND venue_type = 'rooftop bar' AND seated_capacity >= 60", "search_text": "relaxed feel", "standalone_question": "Find a rooftop bar in Glasgow with a relaxed feel for 60 seated guests."}
"""
SYSTEM_PROMPT = _ROUTER_TEMPLATE.replace("{sql_rules}", SQL_RULES)

REPAIR_PROMPT = f"""\
A DuckDB SELECT statement failed. Fix it, so that it answers the question. Return one JSON object \
with the key "sql".

{SQL_RULES}

Schema:
{{schema}}
"""


class RouterPlan(BaseModel):
    intent: Literal["lookup", "list", "aggregate", "policy", "compare", "out_of_scope"]
    tools: list[Literal["query_sql", "search_text"]]
    documents: list[Literal["packages", "venues", "policies"]]
    sql: str | None = None  # one SELECT statement, when tools has "query_sql"
    search_text: str | None = None  # words for the text search, when tools has "search_text"
    standalone_question: str  # the question rewritten with the chat history

    @model_validator(mode="after")
    def _fields_match_tools(self):
        # An error here goes back to the LLM once, through complete_json.
        self.tools = list(dict.fromkeys(self.tools))
        if not self.tools and self.intent != "out_of_scope":
            raise ValueError("tools is empty, but only an out_of_scope plan can have no tools")
        if self.tools and not self.documents:
            raise ValueError("documents is empty, but the tools need at least one document")
        if "query_sql" in self.tools:
            if not (self.sql or "").strip():
                raise ValueError("tools has query_sql, so sql must hold one SELECT statement")
        else:
            self.sql = None
        if "search_text" in self.tools:
            if not (self.search_text or "").strip():
                raise ValueError("tools has search_text, so search_text must hold the search words")
        else:
            self.search_text = None
        return self


def schema_text(sources: Sources) -> str:
    """The table schema for the prompt, with units and the category values from the data."""
    records = {"venues": sources.venues, "packages": sources.packages, "policies": sources.policies}
    lines = []
    for table, columns in TABLES.items():
        lines.append(f"Table {table}: {TABLE_NOTES[table]}.")
        for column, sql_type in columns.items():
            line = f"- {column} {sql_type}: {COLUMN_NOTES[table][column]}."
            if column in CATEGORY_COLUMNS.get(table, []):
                values = sorted({str(r[column]) for r in records[table] if r[column] is not None})
                line += " Values: " + ", ".join(f"'{v}'" for v in values) + "."
            lines.append(line)
        lines.append("")
    packages = ", ".join(f"{p['package_id']} = {p['name']}" for p in sources.packages)
    lines.append(f"Package IDs and names: {packages}.")
    return "\n".join(lines)


def plan_question(
    question: str,
    history: Sequence[dict[str, str]] | None = None,
    *,
    schema: str,
    providers: Sequence[Provider] | None = None,
) -> RouterPlan:
    messages = [
        # replace(), not format(): the examples hold JSON braces.
        {"role": "system", "content": SYSTEM_PROMPT.replace("{schema}", schema)},
        {"role": "user", "content": _user_message(question, history or [])},
    ]
    return complete_json(messages, RouterPlan, providers)


class SqlRepair(BaseModel):
    sql: str


def repair_sql(
    question: str,
    sql: str,
    error: str,
    *,
    schema: str,
    providers: Sequence[Provider] | None = None,
) -> str:
    """Guardrail 6: one LLM call to fix SQL that failed a check or a run."""
    messages = [
        {"role": "system", "content": REPAIR_PROMPT.replace("{schema}", schema)},
        {"role": "user", "content": f"Question: {question}\n\nSQL:\n{sql}\n\nError:\n{error}"},
    ]
    return complete_json(messages, SqlRepair, providers).sql


def _user_message(question: str, history: Sequence[dict[str, str]]) -> str:
    # The history goes in as text, so the model plans the new question and does not answer it.
    turns = [f"{t['role']}: {t['content']}" for t in history[-HISTORY_TURNS:]]
    history_text = "\n".join(turns) if turns else "none"
    return f"Chat history (oldest first):\n{history_text}\n\nQuestion: {question}"
