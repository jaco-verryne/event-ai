"""Part 1: a chat for the sales planners of a fictional UK event company (CLAUDE.md section 7.5),
plus a read-only view of the knowledge base."""

import uuid
from pathlib import Path

import streamlit as st
import yaml

from eventai.rag.display import cited_sources, error_message, fact_rows, hit_rows, router_history, sql_rows
from eventai.rag.pipeline import PipelineResult, ask
from eventai.tracing import trace_url
from eventai.webapp import get_resources

ROOT = Path(__file__).resolve().parent
EXAMPLES = yaml.safe_load((ROOT / "eval" / "part1_questions.yaml").read_text())
CONFIDENCE_COLOURS = {"high": "green", "medium": "orange", "low": "red"}

HOW_IT_WORKS = """\
1. **Router** (one LLM call) reads the question and the chat history. It picks the tools and writes the SQL.
2. **query_sql** runs the SQL on DuckDB behind six guardrails: read-only, one SELECT, known tables, \
a row limit, a timeout and one repair.
3. **search_text** finds meaning in the text fields: Chroma vectors and BM25 keywords, merged with RRF.
4. **Answer** (one LLM call) uses only the tool results. A check in code removes each fact without \
a valid source.

Models: Groq `openai/gpt-oss-120b`, with an OpenRouter free model as the fallback. Embeddings run \
locally (`bge-small-en-v1.5`).

Free model limits allow about two questions a minute. If the limit is reached, wait one minute.
"""

st.set_page_config(page_title="Event AI", page_icon="🎪", layout="wide")


def new_chat() -> None:
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())  # one Langfuse session for each chat


def render_answer(result: PipelineResult, chunks: dict) -> None:
    answer = result.answer
    st.markdown(answer.answer)
    st.badge(f"Confidence: {answer.confidence}", color=CONFIDENCE_COLOURS[answer.confidence])
    if answer.facts:
        st.dataframe(fact_rows(answer), hide_index=True, width="stretch")

    with st.expander(f"Sources ({len(answer.source_ids)})"):
        if not answer.source_ids:
            st.caption("No source in the data supports this answer.")
        for source_id, text in cited_sources(result, chunks):
            st.markdown(f"**{source_id}**")
            st.text(text)

    with st.expander("Debug"):
        st.markdown("**Router plan**")
        st.json(result.plan.model_dump(), expanded=False)
        sql = result.sql
        if sql is not None:
            st.markdown("**SQL (query_sql)**")
            st.code(sql.sql, language="sql")
            if sql.first_error:
                st.caption(f"First error, sent to the LLM for one repair: {sql.first_error}")
            if sql.error:
                st.caption(f"The query failed twice: {sql.error}")
            if sql.added_id_columns:
                st.caption(f"Code added the ID columns {', '.join(sql.added_id_columns)}, so each row can be cited.")
            if sql.truncated:
                st.caption(f"The result had more rows; only the first {len(sql.rows)} are used.")
            if sql.rows:
                st.dataframe(sql_rows(sql), hide_index=True, width="stretch")
            elif not sql.error:
                st.caption("The query returned no rows.")
        if result.plan.search_text is not None:
            st.markdown(f"**Text search (search_text):** `{result.plan.search_text}`")
            if result.hits:
                st.dataframe(hit_rows(result.hits), hide_index=True, width="stretch")
            else:
                st.caption("No text matched above the minimum score.")
        if result.removed_facts:
            st.markdown("**Facts removed by the citation check**")
            st.dataframe([f.model_dump() for f in result.removed_facts], hide_index=True)
        url = trace_url(result.trace_id)
        if url:
            st.link_button("Open the Langfuse trace", url)


def chat_page() -> None:
    if "messages" not in st.session_state:
        new_chat()
    resources = get_resources()
    chunks = {c.chunk_id: c for c in resources.index.chunks}

    with st.sidebar:
        st.header("Example questions")
        for example in EXAMPLES:
            if st.button(example["question"], key=f"example-{example['id']}", width="stretch"):
                st.session_state.pending = example["question"]
        st.divider()
        st.button("New chat", on_click=new_chat, width="stretch")
        with st.expander("How it works"):
            st.markdown(HOW_IT_WORKS)

    st.title("Event AI: venues, packages and booking terms")
    st.caption(
        "A demo for the sales planners of a fictional UK event company. "
        "All data is synthetic. Prices exclude VAT. The Knowledge base page shows the data; "
        "the Part 2 results page shows the last run of the attendee-list agent."
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("error"):
                st.warning(message["content"])
            elif "result" in message:
                render_answer(message["result"], chunks)
            else:
                st.markdown(message["content"])

    question = st.chat_input("Ask about venues, packages or booking terms") or st.session_state.pop("pending", None)
    if question:
        history = router_history(st.session_state.messages)
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Planning, querying and checking the answer..."):
                    result = ask(question, history, resources, session_id=st.session_state.session_id)
            except Exception as err:  # the chat must survive a model limit or an outage
                text = error_message(err)
                st.warning(text)
                st.session_state.messages.append({"role": "assistant", "content": text, "error": True})
            else:
                render_answer(result, chunks)
                st.session_state.messages.append(
                    {"role": "assistant", "content": result.answer.answer, "result": result}
                )


# Explicit navigation, so that the menu says "Chat" and not the file name.
st.navigation([
    st.Page(chat_page, title="Chat", icon="💬", default=True),
    st.Page("pages/knowledge_base.py", title="Knowledge base", icon="📚", url_path="knowledge-base"),
    st.Page("pages/part2_results.py", title="Part 2 results", icon="✅", url_path="part2-results"),
]).run()
