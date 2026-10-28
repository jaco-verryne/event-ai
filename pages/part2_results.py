"""Part 2 results: the last run of the attendee-list agent, from the committed outputs/ (D6). Read-only:
the agent runs in Langflow on the laptop, so this page makes no LLM call and needs no keys."""

import json

import streamlit as st

from eventai.agent import results
from eventai.config import ROOT

FLOW_DIAGRAM = ROOT / "docs" / "diagrams" / "part2-flow.png"
LEGEND = " · ".join(
    f'<span style="background:{colour};color:#000;padding:1px 6px;border-radius:3px">{status}</span>'
    for status, colour in results.STATUS_COLOURS.items()
)

st.title("Part 2: the verified attendee list")
st.caption(
    "The agent reads a Google Calendar event and its RSVP emails, extracts each reply with an LLM, checks and merges "
    "the records in code, and lets an LLM agent decide each flagged record with read-only lookups. It runs in "
    "Langflow on the laptop; this page shows its last run from the committed files in outputs/. "
    "All names, firms and emails are synthetic."
)

run = results.load_outputs()
if run is None:
    st.info("No Part 2 run is committed yet.")
    st.stop()
report = run.report

st.markdown(f"**{results.event_line(report)}**  \nSource: {results.run_source(run.rows)}")
trigger = results.trigger_line(report)
if trigger:
    st.caption(trigger)

for column, (label, value, help_text) in zip(st.columns(6), results.summary_metrics(report)):
    column.metric(label, value, help=help_text)
score = results.latest_score()
if score:
    day, scores = score
    st.markdown(f"**Score** against the expected list, written by hand (`seed/expected_attendees.csv`), on {day}:")
    metrics = results.score_metrics(scores)
    for column, (label, value) in zip(st.columns(len(metrics)), metrics):
        column.metric(label, value)

st.header("Planner brief (from Part 1)")
st.caption(
    "After the list is final, Part 2 asks Part 1, the same RAG pipeline as the chat, about this event. "
    "Code computes each date from the cited policy rule."
)
state, brief = results.brief_view(report)
if state == "error":
    st.warning(f"The brief did not run in this run: {brief}")
elif state == "missing":
    st.caption("This run has no planner brief.")
else:
    st.markdown("\n".join(f"- {line}" for line in brief.get("todo", [])) or "No dated action.")
    for answer in brief["answers"]:
        with st.expander(f"{answer['topic'].capitalize()}: {answer['question']}"):
            if answer.get("error"):
                st.warning(f"Part 1 could not answer: {answer['error']}")
                continue
            st.markdown(answer["answer"])
            st.caption(f"Confidence: {answer.get('confidence', 'unknown')} · "
                       f"Sources: {', '.join(answer.get('source_ids', [])) or 'none'}")
            if answer.get("facts"):
                st.dataframe(answer["facts"], hide_index=True, width="stretch")

st.header("Attendee list")
st.markdown(f"Each value is coloured by its status: {LEGEND}", unsafe_allow_html=True)
st.dataframe(results.attendee_table(run.rows), hide_index=True, width="stretch")
if report.get("no_reply"):
    st.caption(f"Invited, with no reply: {', '.join(report['no_reply'])}")
if report.get("extraction_failed"):
    st.warning(f"Extraction failed for: {', '.join(map(str, report['extraction_failed']))}")

st.header("Flags and agent decisions")
st.caption(
    "The agent proposes a decision for each flag, with a source and a reason. Code accepts a new value only when it "
    "is in the evidence: a source email, a CRM row or the invitee list. Anything else goes to human review."
)
decisions = results.decision_rows(run.rows, run.audit)
if decisions:
    st.dataframe(decisions, hide_index=True, width="stretch")
else:
    st.caption("No record needed the agent in this run.")
if report.get("agent_outputs_rejected"):
    examples = " ".join(report.get("agent_outputs_rejected_examples", []))
    cause = " (the free model's daily limit)" if "free-models-per-day" in examples else ""
    st.caption(f"{report['agent_outputs_rejected']} agent answer(s) could not be used{cause}. "
               "Code sent those flags to human review, and the run went on.")

st.header("One record in detail")
ids = [r["attendee_id"] for r in run.rows]
flagged = [r["attendee_id"] for r in run.rows if r.get("resolution")]
choice = st.selectbox("Attendee", ids, index=ids.index(flagged[0]) if flagged else 0,
                      format_func=lambda i: f"{i} · {next(r['full_name'] for r in run.rows if r['attendee_id'] == i)}")
record = next(r for r in run.rows if r["attendee_id"] == choice)
st.caption(f"Emails: {record['source_keys'].replace(';', ', ')} · CRM: {record.get('crm_id') or 'no match'}")
st.markdown("**Fields:** the value, its status and its source")
st.dataframe(results.field_rows(record), hide_index=True, width="stretch")
st.markdown("**Audit trail:** each check, change, merge and decision for this record")
st.dataframe(results.audit_rows(run.audit, record), hide_index=True, width="stretch")

st.header("Downloads")
files = [("attendees.csv", "text/csv"), ("audit_log.json", "application/json"),
         ("run_report.json", "application/json"), ("planner_brief.md", "text/markdown")]
for column, (name, mime) in zip(st.columns(len(files)), files):
    path = run.folder / name
    if path.exists():
        column.download_button(name, data=path.read_bytes(), file_name=name, mime=mime, width="stretch")

with st.expander("How the run works"):
    st.markdown(
        "1. **Load Event** and **Load RSVP Emails** read Google Calendar and Gmail with read-only access.\n"
        "2. **Extract RSVPs** (LLM) turns each email into fields. **Check Records** (code) checks each value "
        "against its email, normalizes it, merges duplicates, and verifies it against the CRM, the invitee list, "
        "Companies House and the venue capacity.\n"
        "3. A **Loop** sends each flag to the **Agent** (LLM), which can look up the CRM, the invitee list and "
        "Companies House. **Apply Decisions** (code) accepts only values that are in the evidence.\n"
        "4. **Planner Brief** asks Part 1 about this event, and **Write Outputs** writes the files on this page.\n\n"
        "The run command (`python -m eventai.agent.run`) finds the event in Calendar and starts the flow; with "
        "`--watch`, it starts again when new RSVP emails arrive."
    )
    if FLOW_DIAGRAM.exists():
        st.image(str(FLOW_DIAGRAM), caption="The Langflow flow, as wired")
with st.expander("Run report (JSON)"):
    st.json(json.loads(json.dumps(report)), expanded=False)
