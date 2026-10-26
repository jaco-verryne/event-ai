# Event AI

A demo in two parts for a fictional UK event company.

- **Part 1:** a RAG app on the web. It answers questions about venues, packages and booking terms from three structured documents.
- **Part 2:** an agent. It reads a calendar event and RSVP emails. Then it makes a verified attendee list.

All data is synthetic. The full technical summary comes later.

## Live demo

Part 1 runs on Streamlit Community Cloud: https://event-ai-xyp3apsfydznwqktuhvxhu.streamlit.app/

- The free host puts the app to sleep when nobody uses it for some time. If the page says that the app is asleep, click the button to wake it up, then wait about one minute. The first question after a wake-up takes longer, because the app builds its search index again.
- The app uses free models. They allow about two questions a minute. When the limit is reached, the chat says so. Wait one minute, then ask again.
- Use the example questions in the sidebar for a quick test. Open "Sources" and "Debug" under an answer to see the records, the SQL and the search scores.

## Setup

1. Make a virtual environment and install the packages:

   ```bash
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`. Add your API keys.

3. Run the tests:

   ```bash
   pytest
   ```

## Commands

```bash
streamlit run streamlit_app.py                 # Part 1
python -m eventai.agent.run --event-id <id>    # Part 2
python eval/run_part1.py                       # Part 1 scores
```

## Evaluation (Part 1)

The last full run was on 26 Oct 2026, with Groq `openai/gpt-oss-120b`, on the 12 questions in `eval/part1_questions.yaml`. The results are in `eval/results/2026-10-26_part1.json`.

| Metric | Score |
| --- | --- |
| Retrieval hit@5 (no LLM call) | 100% (mean recall@5: 80%) |
| Router tool choice | 83% (10 of 12) |
| SQL result check (result rows, not SQL text) | 100% (11 of 11) |
| Citation check: facts removed | 0 of 28 |
| Answer cites an expected record | 100% |
| Answer accuracy (expected facts in the answer) | 97% (11 of 12 fully correct) |

Known misses:

- Q9 and Q11 use other tools than the evaluation set expects, but give the correct data.
- Q10 (a follow-up question) gives the correct venues and parking values. It writes "does not have parking data recorded" instead of the agreed words "The data does not give".

The first full run on the same day gave 85% answer accuracy. Two changes followed. First, a follow-up question now sends the earlier SQL to the router, which fixed Q10. Second, Q3 and Q6 now accept each correct answer, not one fixed wording or one venue (agreed by Jaco). The SQL score compares the same kind of ID as the reference query, so an extra ID column from a join does not count as an error.
