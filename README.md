# Event AI

A demo in two parts for a fictional UK event company.

- **Part 1:** a RAG app on the web. It answers questions about venues, packages and booking terms from three structured documents.
- **Part 2:** an agent. It reads a calendar event and RSVP emails. Then it makes a verified attendee list.

All data is synthetic. The full technical summary comes later.

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
| SQL result check (result rows, not SQL text) | 91% (10 of 11) |
| Citation check: facts removed | 0 of 33 |
| Answer cites an expected record | 100% |
| Answer accuracy (expected facts in the answer) | 85% (9 of 12 fully correct) |

Known misses:

- Q10 (a follow-up question) kept the city and the capacity, but lost the Gala Dinner filter.
- Q3 and Q6 give correct answers, but with other words than the expected facts.
- Q9 and Q11 use other tools than the evaluation set expects, but give the correct data.
