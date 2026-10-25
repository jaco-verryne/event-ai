import json

import pytest
from pydantic import ValidationError

from eventai.llm import InvalidOutput
from eventai.rag.loaders import TABLES, read_sources
from eventai.rag.router import COLUMN_NOTES, RouterPlan, plan_question, schema_text

SCHEMA = schema_text(read_sources())


def plan(**fields):
    base = {
        "intent": "list",
        "tools": ["query_sql"],
        "documents": ["venues"],
        "sql": "SELECT venue_id FROM venues",
        "search_text": None,
        "standalone_question": "Which venues?",
    }
    return json.dumps({**base, **fields})


def test_valid_plan(fake_provider):
    groq, calls = fake_provider("groq", [plan()])

    result = plan_question("Which venues?", schema=SCHEMA, providers=[groq])

    assert result.tools == ["query_sql"]
    assert result.sql == "SELECT venue_id FROM venues"
    assert len(calls.calls) == 1


def test_plan_without_sql_is_retried(fake_provider):
    groq, calls = fake_provider("groq", [plan(sql=None), plan()])

    result = plan_question("Which venues?", schema=SCHEMA, providers=[groq])

    assert result.sql
    assert len(calls.calls) == 2
    assert "sql must hold" in calls.calls[1]["messages"][-1]["content"]


def test_plan_without_search_words_fails_twice(fake_provider):
    bad = plan(tools=["search_text"], search_text=" ")
    groq, _ = fake_provider("groq", [bad, bad])

    with pytest.raises(InvalidOutput):
        plan_question("Rustic venue?", schema=SCHEMA, providers=[groq])


def test_field_without_its_tool_is_cleared():
    result = RouterPlan.model_validate_json(plan(search_text="rustic"))
    assert result.search_text is None

    both = RouterPlan.model_validate_json(
        plan(tools=["search_text", "query_sql", "search_text"], search_text="rustic")
    )
    assert both.tools == ["search_text", "query_sql"]


def test_out_of_scope_plan_has_no_tools():
    result = RouterPlan.model_validate_json(
        plan(intent="out_of_scope", tools=[], documents=[], sql="SELECT 1")
    )
    assert result.tools == [] and result.sql is None


def test_only_out_of_scope_may_have_no_tools():
    with pytest.raises(ValidationError):
        RouterPlan.model_validate_json(plan(tools=[], sql=None))
    with pytest.raises(ValidationError):
        RouterPlan.model_validate_json(plan(documents=[]))


def test_each_column_has_a_description():
    for table, columns in TABLES.items():
        assert set(columns) == set(COLUMN_NOTES[table]), table


def test_schema_text_lists_tables_columns_and_values():
    for table, columns in TABLES.items():
        assert f"Table {table}:" in SCHEMA
        for column in columns:
            assert f"- {column} " in SCHEMA
    assert "'Leeds'" in SCHEMA
    assert "'converted mill'" in SCHEMA
    assert "'guest numbers'" in SCHEMA
    assert "PKG-05 = Gala Dinner" in SCHEMA


def test_prompt_holds_schema_and_history(fake_provider):
    groq, calls = fake_provider("groq", [plan()])
    history = [
        {"role": "user", "content": "Gala dinner in Leeds?"},
        {"role": "assistant", "content": "The Old Mill fits."},
    ]

    plan_question("Which of those has parking?", history, schema=SCHEMA, providers=[groq])

    messages = calls.calls[0]["messages"]
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    user = messages[-1]["content"]
    assert "Table venues:" in system and "{schema}" not in system
    assert "user: Gala dinner in Leeds?" in user
    assert "assistant: The Old Mill fits." in user
    assert user.endswith("Question: Which of those has parking?")


def test_no_history(fake_provider):
    groq, calls = fake_provider("groq", [plan()])

    plan_question("Which venues?", schema=SCHEMA, providers=[groq])

    assert "Chat history (oldest first):\nnone" in calls.calls[0]["messages"][-1]["content"]
