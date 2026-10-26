"""Knowledge base: the three documents that the chat answers from, as the retrieval tools see them."""

import json

import streamlit as st

from eventai.rag.knowledge import DOCUMENTS, document_chunks, raw_file, table_frame
from eventai.webapp import get_resources

st.title("Knowledge base")
st.caption(
    "The three structured documents that the chat answers from. "
    "All names and data are synthetic. Prices exclude VAT."
)
st.markdown(
    "Each record becomes **one chunk**: nothing is cut, so each answer can cite one row. "
    "**Text fields** go to the meaning search (local embeddings in Chroma) and to the keyword search (BM25). "
    "**Attribute fields** go to SQL on DuckDB tables, for numbers, filters and counts."
)

resources = get_resources()

for tab, document in zip(st.tabs([f"{d.title} ({d.file})" for d in DOCUMENTS]), DOCUMENTS):
    with tab:
        frames = {table: table_frame(resources.con, table) for table in document.tables}
        st.markdown(f"**About this document.** {document.about}")
        st.markdown(
            f"- **Brief example:** {document.brief_example}\n"
            f"- **Records:** {len(frames[document.tables[0]])}\n"
            f"- **Text fields (meaning and keyword search):** {', '.join(document.text_fields)}\n"
            f"- **Attribute fields (SQL):** {', '.join(document.attribute_fields)}"
        )
        with st.expander("Test cases in this document"):
            st.markdown("\n".join(f"- {case}" for case in document.test_cases))

        for table, frame in frames.items():
            st.markdown(f"**Table `{table}`** ({len(frame)} rows, as the SQL sees it)")
            st.dataframe(frame, hide_index=True, width="stretch")

        st.download_button(
            f"Download {document.file}",
            data=raw_file(document),
            file_name=document.file,
            mime=document.mime,
            key=f"download-{document.key}",
        )

        with st.expander("From record to chunk"):
            chunks = {c.record_id: c for c in document_chunks(resources.index.chunks, document)}
            ids = list(chunks)
            record_id = st.selectbox(
                "Record", ids, index=ids.index(document.default_record), key=f"chunk-{document.key}"
            )
            chunk = chunks[record_id]
            st.caption(f"Chunk ID `{chunk.chunk_id}` · locator `{chunk.locator}`")
            left, right = st.columns(2)
            with left:
                st.markdown("**Embedding text** (vectors and BM25: text fields only)")
                st.code(chunk.embedding_text, language=None, wrap_lines=True)
                st.markdown("**Metadata** (filters in Chroma)")
                st.code(json.dumps(chunk.metadata, indent=2), language="json")
            with right:
                st.markdown("**Context text** (what the answer step reads: the full record, with units)")
                st.code(chunk.context_text, language=None, wrap_lines=True)
