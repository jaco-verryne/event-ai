# CLAUDE.md: Event Company AI Challenge

This file gives Claude Code the agreed design for the Inference Group "AI Agent Technical Challenge". Read it at the start of each session.

## 1. Project

- **Owner:** Jaco.
- **Goal:** a well-rounded demo in two parts. It is not a full system.
  - **Part 1:** a RAG app on the web. It answers questions from three structured documents.
  - **Part 2:** an agent. It reads a calendar event and RSVP emails, then makes a verified attendee list. It runs as a Langflow flow on the laptop (D16).
- **Client (fictional):** a UK event company. Its sales planners answer client questions about venues, packages and booking terms.
- **Target:** send the submission pack on Thu 29 Oct 2026. Fri 30 Oct is a buffer day. There is no interview date: the panel reviews the pack, then sets a meeting.
- **Reviewers:** a panel of technical and business people. The pack counts for the TCN Capital role too. Access stays simple: public links, with no sign-in.
- **Source of truth:** the Notion workspace "Inference Group — AI Agent Technical Challenge".
  - Page 2: Architecture & Approach.
  - Page 6: Action Items (tasks by day).
  - Page 7: Knowledge Base Design.
  - Page 8: Future Improvements.
  - Page 9: Architecture & Design (as built). It maps the build to the review criteria.
- If this file and Notion do not agree, stop and ask Jaco.

## 2. How to work

1. Start each session in plan mode.
2. Take the tasks for one day from Notion page 6.
3. Show the plan to Jaco before you write code.
4. Run `pytest` before each commit.
5. Tick each finished task on page 6.
6. Add one line to the progress log on the Notion hub page at the end of a session.
7. Update Notion page 9 with what changed in the build: the section, the evidence, the last scores, and one line in its change log.

Rules:

- Keep the agreed scope. Write new ideas on Notion page 8, not in the code.
- Ask Jaco before you add a dependency that is not in section 4.
- Never commit secrets, OAuth tokens or `.env` files.
- Use synthetic data only. Do not use real personal data (POPIA and UK GDPR).
- Prefer small, plain modules. Do not add frameworks, base classes or plugins "for later".

## 3. Agreed decisions

| ID | Decision |
| --- | --- |
| D1 | Code-first build: Python and Streamlit. Part 2 runs in Langflow (D16), with custom components that wrap the tested code. |
| D2 | Free models only. Groq is the primary provider. OpenRouter free models are the fallback on a rate-limit error. One OpenAI-compatible client. Local embeddings with fastembed. |
| D3 | BM25 plus vector search, on text fields only. Chroma is the vector database. It runs inside the app, with no server. |
| D4 | Host Part 1 on Streamlit Community Cloud, from the GitHub repository. |
| D5 | CSV and JSON only. No tabular PDF. |
| D6 | Part 2 runs on the laptop. The deployed app shows the results of the last run on a read-only page. |
| D7 | A well-rounded demo, not a full system. Cut: PDF loader, Docker, LLM critic step, summary email, MCP server. |
| D8 | Knowledge base: `packages.json`, `venues.csv` and `policies.csv` (section 6). |
| D9 | DuckDB reads the files. The LLM writes the SQL (text-to-SQL), with guardrails (section 8). |
| D10 | Langfuse Cloud (Hobby plan) for traces. A self-hosted server is a future improvement. |
| D11 | Build in Claude Code. Use the claude.ai chat for design, Notion and reviews. |
| D12 | Part 2 resolution is a bounded agent loop: read-only lookups (CRM, invitees, Companies House), at most 3 for each flagged record, then one decision for each flag. Code accepts a value only when it is in the evidence. Orchestrator: the Langflow Agent in a Loop (D16). |
| D13 | Fictional firms only. Companies House "not on the register" is an audit note, not a flag. A failed call gives `web_check_failed`. |
| D14 | Own read-only Calendar and Gmail wrappers on `google-api-python-client`, not the `langchain-google-community` toolkit. |
| D15 | Provider order for each step (section 9). Part 1 and Part 2 extraction: Groq first. Part 2 agent step: OpenRouter Nemotron first, Groq fallback (in Langflow: OpenRouter only, see D16). |
| D16 | Part 2 runs in Langflow 1.13 on the laptop, in its own venv (`.venv-langflow`, `langflow_part2/requirements.txt`). Custom components (category Event Ai) wrap the `eventai` modules; Jaco wires the canvas by hand (`langflow_part2/WIRING.md`). The Langflow Agent cannot fall back to another provider: a missing or invalid decision goes to human review. Part 1 stays plain Python on Streamlit Cloud. LangGraph is not used. |
| D17 | Planner brief: after the list is final, Part 2 asks Part 1's `ask()` (in the Part 1 venv, as a subprocess) about the event: guest numbers, dietary needs, venue and access, and data retention. The answers keep their sources; code computes the dates from the cited policy rules. |
| D18 | Part 2 starts itself: `python -m eventai.agent.run` finds the upcoming events in Calendar and runs the saved Langflow flow through the server API (so the server traces each run). With `--watch`, it runs again when an event's RSVP emails change in Gmail. Publishing the outputs to the website stays a deliberate commit and push. |
| D19 | Inbox noise: the Gmail search finds the emails that name the event, without the account's own mail (`-from:me`). The extraction call also returns `is_rsvp`; code keeps an email that is not an RSVP (an auto-reply, a supplier) off the list, with an audit entry and a line in the run report. Only an explicit `false` skips an email. |

## 4. Stack

Use these packages only, unless Jaco agrees to more:

| Package | Use |
| --- | --- |
| Python 3.12 | Runtime |
| `openai` | One client for Groq, OpenRouter and (later) Azure OpenAI |
| `pydantic` | All schemas and the validation of LLM output |
| `fastembed` | Local embeddings, model `BAAI/bge-small-en-v1.5` |
| `chromadb` | Vector search with metadata filters |
| `rank-bm25` | Keyword search |
| `duckdb` | Tables and SQL |
| `sqlglot` | The SQL check before a query runs |
| `pandas` | Data generation and display |
| `phonenumbers` | Phone numbers in E.164 format |
| `rapidfuzz` | Fuzzy match for deduplication |
| `google-api-python-client`, `google-auth-oauthlib` | Calendar and Gmail |
| `requests`, `tenacity` | Companies House calls, retries with backoff |
| `langfuse` | Traces |
| `streamlit` | Web interface |
| `pytest`, `pyyaml` | Tests and the evaluation files |

Keep `requirements.txt` at the repository root, because Streamlit Community Cloud reads it.

Part 2 runs in Langflow (D16), in its own venv `.venv-langflow` from `langflow_part2/requirements.txt` (`langflow==1.13.0`, `langchain-groq`). Langflow pins older `duckdb`, `langfuse` and `pydantic` than Part 1, so the two venvs stay apart. The `eventai` modules run in both.

## 5. Repository layout

```
.
├── CLAUDE.md
├── README.md                    # also the technical summary: the part above <!-- end of summary --> is the PDF
├── requirements.txt
├── .env.example
├── .gitignore                   # .env, token*.json, credentials.json, .chroma/, *.duckdb
├── .streamlit/
│   └── secrets.toml.example
├── streamlit_app.py             # entry point: st.navigation and the Part 1 chat page
├── pages/
│   ├── knowledge_base.py        # read-only view of the three documents and their chunks
│   └── part2_results.py         # read-only view of outputs/ (register it in st.navigation)
├── data/
│   ├── packages.json            # written by hand
│   ├── policies.csv             # written by hand
│   ├── venues_input.yaml        # names and descriptions for the generator
│   ├── generate_venues.py       # fixed random seed
│   └── venues.csv               # generated, committed
├── eventai/
│   ├── config.py                # settings from .env or st.secrets
│   ├── llm.py                   # client with the Groq -> OpenRouter fallback
│   ├── tracing.py               # Langfuse setup
│   ├── webapp.py                # cached resources that both app pages share
│   ├── rag/
│   │   ├── display.py           # chat helpers: rows, sources, history, error messages
│   │   ├── knowledge.py         # Knowledge base page helpers
│   │   ├── loaders.py           # DuckDB tables and chunks
│   │   ├── chunks.py            # Chunk model, embedding text, context text
│   │   ├── search_text.py       # Chroma + BM25 + RRF
│   │   ├── query_sql.py         # guardrails and execution
│   │   ├── router.py            # RouterPlan
│   │   ├── answer.py            # Answer model and citation check
│   │   └── pipeline.py          # ask(question, history) -> Answer
│   └── agent/
│       ├── tools/
│       │   ├── __init__.py      # ToolError, timeout, retries with backoff
│       │   ├── google_auth.py   # sign-in, services, request execution with retries
│       │   ├── calendar.py
│       │   ├── gmail.py
│       │   ├── companies_house.py
│       │   └── seed_files.py    # the seed files as a source (--source seed), the CRM, venue capacity
│       ├── schema.py            # ExtractedRsvp, FieldValue, Attendee, Event, Email, Record, AuditEntry
│       ├── extract.py           # LLM extraction: prompt, parse, one retry (any model)
│       ├── checks.py            # grounding, normalization, deduplication, verification (plain code)
│       ├── output.py            # attendees.csv, audit_log.json, run_report.json
│       ├── review.py            # the agent step: review queue, instructions, code check of decisions
│       ├── brief.py             # the planner brief: Part 2 asks Part 1 (D17)
│       ├── run.py               # the run command and the Gmail watcher (D18)
│       ├── results.py           # helpers for the Part 2 results page
│       ├── lookups.py           # the agent tools: CRM, invitee list, Companies House
│       └── flow_io.py           # Langflow tables and Data to plain dicts
├── langflow_part2/              # Part 2 in Langflow (D16)
│   ├── requirements.txt         # the Langflow venv (.venv-langflow)
│   ├── serve.sh                 # start Langflow on http://localhost:7860
│   ├── WIRING.md                # how to wire the flow by hand
│   ├── components/event_ai/     # custom components, one file each
│   ├── smoke.sh                 # smoke test of the components, no LLM call
│   └── .data/                   # Langflow database (gitignored)
├── seed/
│   ├── seed_google.py           # makes the event and inserts the RSVP emails
│   ├── event.yaml               # the event, its invitees and its venue
│   ├── rsvp_emails.yaml         # the seed emails, with known defects
│   ├── late_rsvp.yaml           # a late reply for the watcher demo (seed_google.py --late)
│   ├── noise_emails.yaml        # emails that are not RSVPs (seed_google.py --noise, D19)
│   ├── crm.csv                  # reference data
│   ├── expected_attendees.csv   # expected output for the Part 2 score
│   └── expected_late.csv        # expected row of the late reply (scored when the run has it)
├── eval/
│   ├── part1_questions.yaml
│   ├── run_part1.py
│   └── run_part2.py
├── outputs/                     # last Part 2 run: attendees.csv, audit_log.json, run_report.json
├── docs/
│   ├── diagrams/                # draw.io files, the Python scripts that build them, and the PNG exports
│   ├── build_summary_pdf.py     # README summary -> PDF (markdown-it-py and headless Chrome)
│   └── Event-AI-technical-summary.pdf   # the 2-page summary (S2), committed
└── tests/
```

The entry point `streamlit_app.py` stays at the root. Then `import eventai` works on Streamlit Community Cloud.

## 6. Knowledge base (Part 1)

Notion page 7 has the full design. Summary:

| File | Brief example | Size | Text fields (embed) | Attribute fields (SQL) |
| --- | --- | --- | --- | --- |
| `packages.json` | Product specifications | 8 packages | name, description, includes, add-ons | package_id, guest limits, price, lead time |
| `venues.csv` | Dataset | about 120 rows | name, venue_type, description | venue_id, city, capacities, day rate, access, parking |
| `policies.csv` | Policy table | about 25 rows | condition, rule | policy_id, area, applies_to |

Columns:

- `venues.csv`: `venue_id, name, city, venue_type, description, seated_capacity, standing_capacity, day_rate_gbp, step_free_access, parking_spaces, av_included, catering, nearest_station, walk_minutes`
- `policies.csv`: `policy_id, area, applies_to, condition, rule, effective_from`
- `packages.json`: a list under `packages`. Each object has `package_id, name, event_type, description, min_guests, max_guests, price_per_head_gbp, includes[], add_ons[{name, price_gbp}], lead_time_weeks, suitable_venue_types[]`.

Prices exclude VAT. All names are fictional.

Test cases that the data must contain:

1. Two similar names: "The Old Mill" (Leeds) and "Old Mill Studios" (Manchester).
2. Two IDs that differ by one character: `PKG-01` and `PKG-07`.
3. One venue with no parking value (venue `V045`).
4. Cancellation bands with exact limits. A cancellation exactly 30 days before the event falls in one band only.
5. One rule for one package only: final guest numbers for the Gala Dinner are due earlier than for other packages.
6. Venues in Leeds with outdoor space in the description (courtyard, rooftop terrace, garden), but with no word "outdoor".

## 7. Part 1 design

### 7.1 Ingestion

- Build the DuckDB file at start-up from the three files, in a new temporary folder for each build. Then reopen it in read-only mode. (A fixed path fails on Streamlit Cloud: a code reload keeps the old read-only connection open, and DuckDB refuses a write connection to the same file.)
- `packages.json` gives two tables: `packages`, and `package_items` (the included items and the add-ons, with a `kind` column).
- Make one chunk per CSV row and one chunk per package. Do not cut records into smaller pieces.
- Each chunk has two texts:
  - **Embedding text:** text fields only. Example: `The Old Mill. Converted mill. Converted Victorian mill with exposed brick and a courtyard.`
  - **Context text:** the full record as `label: value` lines with units. The answer step sees this text.
- Embed the chunks once at start-up (about 150 chunks). Cache the Chroma collection and the BM25 index with `st.cache_resource`.

```python
class Chunk(BaseModel):
    chunk_id: str        # "venues.csv#V012"
    source: str          # "venues.csv"
    record_id: str       # "V012"
    locator: str         # "row 12" or "$.packages[2]"
    embedding_text: str
    context_text: str
    metadata: dict[str, str | int | float | bool]
```

### 7.2 Router

One LLM call per question. The router writes the SQL inside its plan. The prompt holds the table schema, with column descriptions and units.

```python
class RouterPlan(BaseModel):
    intent: Literal["lookup", "list", "aggregate", "policy", "compare", "out_of_scope"]
    tools: list[Literal["query_sql", "search_text"]]
    documents: list[Literal["packages", "venues", "policies"]]
    sql: str | None = None            # one SELECT statement, when tools has "query_sql"
    search_text: str | None = None    # words for the text search, when tools has "search_text"
    standalone_question: str          # the question rewritten with the chat history
```

### 7.3 Tools

```python
def query_sql(sql: str) -> SqlResult: ...
# Runs only after the guardrails in section 8. Returns columns, rows and record IDs.

def search_text(query: str, documents: list[str],
                record_ids: list[str] | None = None, k: int = 5) -> list[SearchHit]: ...
# Chroma vector search and BM25, merged with reciprocal rank fusion (RRF).
# record_ids limits the search to the rows that query_sql returned.
```

Rules:

- Use `query_sql` for numbers, categories, IDs, counts, minimum and maximum values.
- Use `search_text` for meaning in the text fields.
- For a mixed question, run `query_sql` first. Then run `search_text` with a Chroma filter on the record IDs (`{"record_id": {"$in": ids}}`).
- For a policy question with ranges, the SQL must select all rules of the policy area.
- `search_text` has a minimum score. Below it, the answer says that the data does not have the answer.

### 7.4 Answer

One LLM call. The model uses only the tool results.

```python
class Fact(BaseModel):
    label: str
    value: str
    source_id: str       # "venues.csv#V012"

class Answer(BaseModel):
    answer: str
    facts: list[Fact]
    source_ids: list[str]
    confidence: Literal["high", "medium", "low"]
```

- A check in code confirms that each `source_id` was in the tool results. Remove a fact that fails the check.
- When a value is empty in the data, the answer says that the data does not give the value.
- When prices appear, the answer says that they exclude VAT.

### 7.5 Streamlit UI

- A chat with two expanders: "Sources" and "Debug" (router plan, SQL, tool results, search scores).
- Buttons with example questions from the evaluation set.
- A clear message when the free daily limit is reached.

## 8. SQL guardrails (D9)

Implement all six rules in `query_sql.py`. Each rule needs a unit test.

1. Open DuckDB in read-only mode.
2. Parse the SQL with `sqlglot` (dialect `duckdb`). Allow exactly one statement, and only a SELECT.
3. Allow only the known tables (`venues`, `packages`, `package_items`, `policies`) and their columns. Reject table functions, for example `read_csv`.
4. Wrap the query with a row limit of 200.
5. Run the query in a worker thread. Call `con.interrupt()` after 5 seconds.
6. On an error, send the error to the LLM once for a repair. After a second error, the answer says that it cannot answer.

The debug panel shows the SQL and the result rows.

## 9. LLM client (D2)

- One `openai.OpenAI` client per provider:
  - Groq: `base_url="https://api.groq.com/openai/v1"`, model `openai/gpt-oss-120b`.
  - OpenRouter: `base_url="https://openrouter.ai/api/v1"`, a `:free` model that supports JSON output. Check the current list on openrouter.ai.
- On HTTP 429 from the first provider, retry the same request on the second provider.
- Use `temperature=0` and JSON output. Validate each output with Pydantic. Retry once on invalid output.
- Provider order for each step (D15):

  | Step | First | Fallback |
  | --- | --- | --- |
  | Part 1 router, answer, SQL repair | Groq `openai/gpt-oss-120b` | OpenRouter `nvidia/nemotron-3.5-super-vl:free` |
  | Part 2 extraction (about 13 calls a run) | Groq `openai/gpt-oss-120b` | OpenRouter `nvidia/nemotron-3.5-super-vl:free` |
  | Part 2 agent step (resolution) | OpenRouter `nvidia/nemotron-3.5-super-vl:free` | Groq `openai/gpt-oss-120b` |

  Reason: in the spike on 27 Oct, Nemotron gave a correct structured decision first time; gpt-oss failed on that path. OpenRouter free models allow 50 requests a day (fewer than 10 credits bought), so only the low-volume agent step uses OpenRouter first.
- Try a smaller model for the router only if the evaluation score stays the same.
- Budget: a Part 1 question uses two calls (router and answer). An SQL repair adds one call.

## 10. Part 2 design

### 10.1 Flow

One command starts a full run: `python -m eventai.agent.run` (D18). It finds the upcoming events in Calendar (a `Venue: V…` line in the description), or takes `--event-id <id>`, and runs the saved Langflow flow through the server API. `--watch` checks Gmail every few minutes and runs an event again when its RSVP emails change (state in `.watch_state.json`). The run has no human step; the trigger (`command` or `watch`, with the reason) goes into the run report.

1. **Calendar tool:** get the event, the invitee list and the venue ID (from the event description).
2. **Email tool:** get the emails that name the event (a Gmail search, without the account's own mail).
3. **Extraction (LLM):** one call per email, into `ExtractedRsvp`. One retry on invalid output. The call also says whether the email is an RSVP; code keeps a non-RSVP off the list, with an audit entry (D19).
4. **Grounding check (code):** each extracted value must appear in its source email (fuzzy match). A value with no support gets a flag.
5. **Normalization (code):** name case, lower-case emails, E.164 phone numbers (default region GB), standard company suffixes (Ltd, Limited, PLC).
6. **Deduplication (code):** exact match on email first, then fuzzy match on name and company. Keep the source of each value.
7. **Verification (code and tools):** format rules, the CRM export (`seed/crm.csv`), Companies House, and the capacity in `venues.csv`.
8. **Resolution (LLM agent, flagged records only, D12):** read-only lookups (CRM, invitees, Companies House), at most 3 for each record, then one decision for each flag: use a value, keep the value, or send the record to human review, with a reason. Code accepts a value only when it is in the evidence. Provider order: OpenRouter Nemotron first, Groq fallback (D15).
9. **Output:** `outputs/attendees.csv`, `outputs/audit_log.json` and `outputs/run_report.json`.

### 10.2 Schemas

```python
class ExtractedRsvp(BaseModel):
    is_rsvp: bool | None = True   # D19: only an explicit False skips the email
    full_name: str | None
    email: str | None
    phone: str | None
    company: str | None
    job_title: str | None
    dietary_needs: str | None
    attending: bool | None

FieldStatus = Literal["verified", "corrected", "absent", "conflict"]

class FieldValue(BaseModel):
    value: str | None
    status: FieldStatus
    source: str            # "gmail:<message_id>", "crm.csv#C014" or "companies_house:<number>"
    note: str | None = None

class Attendee(BaseModel):
    attendee_id: str
    full_name: FieldValue
    email: FieldValue
    phone: FieldValue
    company: FieldValue
    company_number: FieldValue
    job_title: FieldValue
    dietary_needs: FieldValue
    attending: FieldValue        # "yes", "no", or absent when unclear
    flags: list[str] = []
    source_keys: list[str] = []  # the emails merged into this record
    candidates: dict[str, list[FieldValue]] = {}  # the values of a field in conflict
    crm_id: str | None = None
    resolutions: list[str] = []  # "<flag>:<action>", from the agent step
```

`eventai/agent/schema.py` also holds `Event`, `Invitee`, `Email`, `CrmContact`, `Record` (one email after the code checks) and `AuditEntry`.

Rules in `checks.py`, beyond the flow above:

- Status: `verified` (in the source and passed the checks), `corrected` (changed by a rule, with the old value in the note), `absent` (no source has a value), `conflict` (sources disagree, or the value fails a check).
- A conflict that the CRM settles (the CRM value equals exactly one candidate) is a rule, so code settles it. The agent gets only judgement calls.
- Info flags (`phone_absent`, `web_check_failed`) go to the run report only. Every other flag sends the record to the agent step.
- Attendee IDs follow the date of the first email.

### 10.3 Flow (Langflow, D16)

- Components (`langflow_part2/WIRING.md` has the 21 connections): Chat Input → Load Event → Load RSVP Emails → Extract RSVPs (Groq primary, OpenRouter fallback) → Check Records → Loop over the review queue (Type Convert → Agent with CRM Lookup, Invitee Lookup and Company Search, on OpenRouter Nemotron) → Apply Decisions → Write Outputs → Chat Output.
- The Loop runs the Agent once for each review flag (Max Iterations 4, no chat history). The Agent's Structured Response goes back into the Loop; Done passes all the decisions to Apply Decisions.
- Extraction retries once on invalid output, then tries the fallback model. A failed email is in the run report.
- The Langflow server sends one Langfuse trace for each run (environment `agent`), with a span for each component and the LLM calls. `lfx run` sends no trace, so the run command calls the server API.

### 10.4 Rules

- The LLM works in two steps only: Extract RSVPs and the Agent. All other components are plain code.
- Each tool call has a timeout and retries with backoff (`tenacity`).
- A failed tool does not stop the run. The affected records get a flag, for example `web check failed`.
- The audit log records the source of each value, each change, each rule result and each resolution reason.
- Do not invent values. An absent value stays empty, with the status `absent`.

### 10.5 Google access

- Agent scopes (read-only): `https://www.googleapis.com/auth/calendar.readonly` and `https://www.googleapis.com/auth/gmail.readonly`. Token file: `token.json`.
- Seed scopes (write): `https://www.googleapis.com/auth/calendar.events` and `https://www.googleapis.com/auth/gmail.insert`, plus `gmail.readonly`, so a second seed run skips the emails already there. Token file: `token_seed.json`. Only `seed/seed_google.py` uses them. It sends nothing: no invitations (`sendUpdates="none"`), and the emails are inserted, not sent.
- Setup steps for the demo account: `seed/GOOGLE_SETUP.md`.
- Use a separate Google demo account. The consent screen stays in Testing status, with the demo account as a test user.
- In Testing status, refresh tokens expire after 7 days. Sign in again before a demo.

### 10.6 Companies House

- Base URL: `https://api.company-information.service.gov.uk`. Basic auth, with the API key as the user name and an empty password.
- Use `/search/companies?q=<name>` for a name, and `/company/<number>` for the status.
- Cache each response in memory for the run.
- The seed firms are fictional (D13), so the check returns "not on the register". That result is an audit note, not a flag. A failed call gives the flag `web_check_failed`.

### 10.7 Seed data

- One calendar event, about 12 RSVP emails, and `seed/crm.csv`.
- Known defects: duplicates, typos, a nickname, mixed-case emails, an absent phone number, a substitute attendee who is not on the invitee list, and a company name that differs from the CRM (D13).
- Synthetic only: invented names, fictional firms, `.example` email domains, and phone numbers from the Ofcom drama ranges. Use the geographic ranges (for example 0113 496 0xxx); `phonenumbers` rejects the mobile range 07700 900xxx as invalid.
- Inbox noise (`seed/noise_emails.yaml`, D19): an out-of-office reply and a supplier quote that name the event (the extraction marks them not RSVPs), and a newsletter and an advert that do not (the search leaves them out). `eval/run_part2.py` checks that they stay off the list and that no RSVP is skipped.
- Write `seed/expected_attendees.csv` by hand. `eval/run_part2.py` measures the precision and recall of the flags against it.

## 11. Evaluation

`eval/part1_questions.yaml` holds 12 questions (Notion page 7). Format:

```yaml
- id: 6
  type: filter_and_meaning
  question: Suggest a venue in Leeds with outdoor space for a summer party.
  expected_tools: [query_sql, search_text]
  expected_record_ids: [V0xx, V0yy]
  expected_facts: []
  expected_facts_any: ["The Old Mill", "Roundhay Hall"]   # any one counts (26 Oct)
```

Other fields in the file: `accepted_tools` (other tool sets that count as correct), `reference_sql` (checked by a test against the data) and `follow_up_of` (the scorer sends that turn as history).

Metrics:

- Tool choice: the router selects the expected tools.
- SQL result check: the result rows match the expected rows.
- Retrieval hit rate: an expected record is in the `search_text` results. This needs no LLM call.
- Citation check: each cited ID is in the tool results.
- Answer accuracy: the expected facts appear in the answer.

Write the scores to `eval/results/` with the date. The README shows the last scores.

## 12. Configuration

`.env.example`:

```
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
COMPANIES_HOUSE_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
GOOGLE_CLIENT_SECRET_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
LANGFLOW_URL=http://127.0.0.1:7860
LANGFLOW_API_KEY=
```

`config.py` reads `st.secrets` first, then the environment.

## 13. Deployment (Streamlit Community Cloud)

- Main file: `streamlit_app.py`. Python 3.12 in the advanced settings.
- Put the keys in the Streamlit secrets. Part 1 needs the LLM keys and the Langfuse keys only.
- Risk: in the past, Chroma needed a newer SQLite version than the host image had. If the deploy fails on SQLite, add `pysqlite3-binary` to `requirements.txt` and put this at the top of `streamlit_app.py`:

```python
__import__("pysqlite3")
import sys
sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
```

- The host puts idle apps to sleep. The README and the submission email must tell reviewers how to wake the app.

## 14. Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/generate_venues.py          # make venues.csv
streamlit run streamlit_app.py          # Part 1
python seed/seed_google.py              # one time: seed the demo account
langflow_part2/serve.sh                # Part 2: Langflow on http://localhost:7860
langflow_part2/smoke.sh                # Part 2 components, no LLM call
python -m eventai.agent.run            # Part 2: find the events in Calendar and run the flow (D18)
python -m eventai.agent.run --watch --every 60   # run again when RSVP emails change
python seed/seed_google.py --late       # the watcher demo: insert the late RSVP (once)
python seed/seed_google.py --noise      # insert the emails that are not RSVPs (once, D19)
pytest                                  # tests
python eval/run_part1.py                # Part 1 scores
python eval/run_part2.py                # Part 2 scores
python docs/build_summary_pdf.py        # the 2-page summary PDF from README.md
```

## 15. Definition of done

Part 1:

- The app answers the 12 evaluation questions, with sources.
- The debug panel shows the plan, the SQL and the search scores.
- The app runs on Streamlit Community Cloud.
- The scores are in `eval/results/` and in the README.

Part 2:

- One command makes `outputs/attendees.csv`, the audit log and the run report.
- Each field has a status and a source.
- The precision and recall of the flags are in the README.
- One Langfuse trace shows a full run.

## 16. Writing rules

- Write the README and the docs in ASD-STE100 Simplified Technical English: short sentences, active voice, simple tenses, one word for one meaning.
- Keep code comments short. Explain why, not what.
- Commit messages: imperative and short, for example `Add SQL guardrails`.
