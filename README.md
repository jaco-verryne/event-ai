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
```
