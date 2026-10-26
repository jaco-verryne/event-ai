"""The resources that both pages of the Streamlit app share."""

import streamlit as st

from eventai.rag.pipeline import Resources, load_resources
from eventai.tracing import init_tracing


@st.cache_resource(show_spinner="Loading the knowledge base and the search index...")
def get_resources() -> Resources:
    # Built once per server process and shared by all pages: DuckDB, Chroma, BM25, schema text.
    init_tracing(environment="app")
    return load_resources()
