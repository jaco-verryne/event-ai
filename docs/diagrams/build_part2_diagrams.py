"""Build docs/diagrams/event-ai-part2.drawio (4 pages): Part 2 as built in Langflow (D16).

    python docs/diagrams/build_part2_diagrams.py docs/diagrams/event-ai-part2.drawio

Pages 1, 2 and 4 are drawn here. Page 3 (the agent loop for one flag) is laid out by the
draw.io skill's seqlayout.py from agent-loop.json, then coloured here:

    python3 <drawio-skill>/scripts/seqlayout.py docs/diagrams/agent-loop.json -o docs/diagrams/agent-loop.drawio
"""

import re
import sys
from pathlib import Path

from drawio_kit import (BOX, CODE, CONTEXT, CYL, DASHED, EDGE, FILE, LANE, LLM, META, STORE, Page,
                        add_style, mxfile)

OUT = Path(sys.argv[1])
NOTE = "shape=note;whiteSpace=wrap;html=1;size=14;fontSize=11;align=left;spacingLeft=8;spacingRight=8;" + CONTEXT
WHITE = "fillColor=#ffffff;strokeColor=#000000;"
LOOP = EDGE + "strokeColor=#9673a6;strokeWidth=2;"
DOWN = "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
RIGHT = "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
BOTH = "startArrow=block;startFill=1;startSize=8;"

# Page 1: architecture
p1 = Page("1 · Part 2 architecture")
p1.title("t", "Event AI · Part 2 architecture (attendee-list agent in Langflow)", w=900)

p1.v("src", "Event inputs (one source per run)", LANE + META, 40, 70, 220, 330)
p1.v("cal", "<b>Google Calendar</b><br>event · invitees · venue ID<br><i>calendar.readonly</i>", BOX + META, 20, 40, 180, 70, "src")
p1.v("gm", "<b>Gmail</b><br>RSVP emails<br><i>gmail.readonly</i>", BOX + META, 20, 130, 180, 70, "src")
p1.v("seed", "<b>Seed files</b> (offline source)<br>seed/event.yaml<br>seed/rsvp_emails.yaml", BOX + FILE + "dashed=1;", 20, 230, 180, 80, "src")

p1.v("ref", "Reference data", LANE + FILE, 40, 460, 220, 200)
p1.v("ven", "<b>venues.csv</b><br>seated capacity (Part 1 data)", BOX + FILE, 20, 40, 180, 60, "ref")
p1.v("crm", "<b>crm.csv</b><br>known contacts", BOX + FILE, 20, 120, 180, 60, "ref")

p1.v("run", "Langflow 1.13 flow on the laptop · own venv · run command", LANE + "fillColor=#ffffff;strokeColor=#6c8ebf;", 330, 70, 420, 700)
p1.v("fetch", "<b>Load Event · Load RSVP Emails</b> (code)<br>event, invitees, venue ID<br>emails with Date and Message-ID<br>10 s timeout · 3 retries", BOX + CODE, 40, 50, 340, 170, "run")
p1.v("extract", "<b>Extract RSVPs</b> (LLM, one call per email)<br>free text → ExtractedRsvp · one retry, then the fallback model", BOX + LLM, 40, 260, 340, 60, "run")
p1.v("checks", "<b>Check Records</b> (code)<br>skip non-RSVPs · ground · normalize · dedupe · verify<br>CRM · invitees · capacity · Companies House", BOX + CODE, 40, 360, 340, 90, "run")
p1.v("agent", "<b>Loop → Agent → Agent Decision</b> (flagged records only)<br>3 read-only tools · ≤ 3 calls for each flag<br><b>Apply Decisions</b> (code) checks each fix", BOX + LLM, 40, 490, 340, 90, "run")
p1.v("write", "<b>Planner Brief → Write Outputs</b> (code)<br>Part 1 answers with sources · status and source for each field", BOX + CODE, 40, 620, 340, 60, "run")

p1.v("ext", "External services", LANE + META, 800, 70, 260, 690)
p1.v("lf", "<b>Langfuse Cloud</b><br>one trace per run (Langflow server)", BOX + META, 20, 40, 220, 70, "ext")
p1.v("llm", "<b>LLM providers</b> (free)<br>Groq gpt-oss-120b: extraction<br>OpenRouter Nemotron: agent step,<br>extraction fallback", BOX + META, 20, 220, 220, 120, "ext")
p1.v("ch", "<b>Companies House API</b><br>company search · cached per run<br>fictional firms: \"not on the register\" note", BOX + META, 20, 400, 220, 100, "ext")
p1.v("p1rag", "<b>Part 1 RAG pipeline</b><br>ask() in the Part 1 venv (subprocess)<br>4 questions → cited answers", BOX + CODE, 20, 580, 220, 90, "ext")

p1.v("out", "<b>outputs/</b> (committed)<br>attendees.csv · audit_log.json<br>run_report.json · planner_brief.md", CYL + STORE, 410, 820, 260, 90)
p1.v("app", "<b>Streamlit app</b> (Community Cloud)<br>Part 2 results page · read-only", BOX + WHITE, 820, 830, 240, 70)
p1.v("score", "<b>eval/run_part2.py</b> (code)<br>flag precision and recall<br>vs seed/expected_attendees.csv", BOX + CODE, 40, 825, 260, 80)

p1.e("e1", "cal", "fetch", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.206;")
p1.e("e2", "gm", "fetch", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.735;")
p1.e("e3", "seed", "fetch", "Source = seed", style=DASHED, points=[(300, 340), (300, 273)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.9;")
p1.e("e4", "fetch", "extract", extra=DOWN)
p1.e("e5", "extract", "checks", extra=DOWN)
p1.e("e6", "checks", "agent", "review queue", extra=DOWN)
p1.e("e7", "agent", "write", extra=DOWN)
p1.e("e8", "crm", "checks", points=[(320, 595), (320, 505)], extra="exitX=1;exitY=0.25;entryX=0;entryY=0.833;")
p1.e("e9", "crm", "agent", points=[(345, 625), (345, 578)], extra="exitX=1;exitY=0.75;entryX=0;entryY=0.2;")
p1.e("e10", "ven", "checks", points=[(300, 530), (300, 490)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.667;")
p1.e("e11", "extract", "llm", "LLM calls", style=DASHED, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.38;")
p1.e("e12", "checks", "ch", extra="exitX=1;exitY=0.667;entryX=0;entryY=0.2;")
p1.e("e13", "agent", "llm", "", style=DASHED, points=[(1050, 632), (1050, 350)], extra="exitX=1;exitY=0.8;entryX=1;entryY=0.5;")
p1.e("e14", "agent", "ch", "company_search tool", points=[(930, 614)], extra="exitX=1;exitY=0.6;entryX=0.5;entryY=1;")
p1.e("e15", "run", "lf", "traces", style=DASHED, extra="exitX=1;exitY=0.107;entryX=0;entryY=0.5;")
p1.e("e16", "write", "out", extra=DOWN)
p1.e("e17", "out", "app", "git push", extra=RIGHT)
p1.e("e18", "out", "score", "scored by", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
p1.e("e19", "write", "p1rag", "", style=EDGE + BOTH, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.722;")
p1.v("why", "<b>Code does the checks; the LLM extracts and judges.</b><br>The agent runs only for flagged records. "
     "Its tools are read-only, it makes at most 3 calls for each flag, and code accepts a fix only "
     "when the value is in the evidence.", NOTE, 1110, 330, 300, 130)
p1.v("why2", "<b>Each Event AI component wraps a tested module</b> (eventai.agent). The canvas only wires them. "
     "The same modules run in the unit tests and in the smoke test.", NOTE, 1110, 500, 300, 100)
p1.legend("lg", 1110, 110, [(FILE, "Data file"), (STORE, "Output files"), (CODE, "Code step"),
                            (LLM, "LLM step"), (META, "External service")])

# Page 2: the Langflow flow, as wired on the canvas (langflow_part2/WIRING.md)
p2 = Page("2 · The Langflow flow")
p2.title("t", "Event AI · Part 2 flow in Langflow: components and connections", w=900)
COL_X, COL_W = 300, 260
main = [
    ("chat", "<b>Chat Input</b><br>partnersummit2026", META, 70, 50),
    ("ev", "<b>Load Event</b> (code)<br>Source = google: Calendar, read-only<br>event · invitees · venue ID", CODE, 150, 70),
    ("em", "<b>Load RSVP Emails</b> (code)<br>Gmail search, read-only<br>emails with Date and Message-ID", CODE, 250, 70),
    ("ex", "<b>Extract RSVPs</b> (LLM)<br>one call per email → ExtractedRsvp<br>one retry, then the fallback model", LLM, 350, 70),
    ("ck", "<b>Check Records</b> (code)<br>ground · normalize · dedupe · verify<br>outputs: Checked records,<br>Review queue (one item per flag)", CODE, 460, 80),
    ("loop", "<b>Loop</b><br>Item: one flag at a time<br>Done: all the decisions", CONTEXT, 600, 70),
    ("ap", "<b>Apply Decisions</b> (code)<br>is the value in the evidence?<br>no → human review, with a reason", CODE, 940, 70),
    ("pb", "<b>Planner Brief</b> (code)<br>asks Part 1 four questions<br>code computes the dates", CODE, 1050, 70),
    ("wo", "<b>Write Outputs</b> (code)<br>status and source for each field<br>audit log · run report", CODE, 1160, 70),
    ("co", "<b>Chat Output</b><br>summary and dated actions", META, 1270, 50),
]
for nid, label, style, y, h in main:
    p2.v(nid, label, BOX + style, COL_X, y, COL_W, h)
for a, b in [("chat", "ev"), ("ev", "em"), ("em", "ex"), ("ex", "ck"), ("ap", "pb"), ("pb", "wo"), ("wo", "co")]:
    p2.e(f"{a}-{b}", a, b, extra=DOWN)
p2.e("queue", "ck", "loop", "Review queue", extra=DOWN)
p2.e("done", "loop", "ap", "Done", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
# The other inputs of Check Records and Apply Decisions run down the left side, nested so they do not cross.
p2.e("ev-ck", "ev", "ck", "Event", points=[(250, 185), (250, 520)], extra="exitX=0;exitY=0.5;entryX=0;entryY=0.75;")
p2.e("em-ck", "em", "ck", "Emails", points=[(270, 285), (270, 490)], extra="exitX=0;exitY=0.5;entryX=0;entryY=0.375;")
p2.e("ck-ap", "ck", "ap", "Checked records", points=[(220, 532), (220, 975)], extra="exitX=0;exitY=0.9;entryX=0;entryY=0.5;")

p2.v("groq", "<b>Language Model · Groq</b><br>openai/gpt-oss-120b · temperature 0", BOX + META, 640, 330, 220, 56)
p2.v("or", "<b>Language Model · OpenRouter</b><br>nvidia/nemotron-3.5-super-vl:free", BOX + META, 640, 400, 220, 56)
p2.e("groq-ex", "groq", "ex", "primary", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.25;")
p2.e("or-ex", "or", "ex", "fallback", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.75;")
p2.e("or-ag", "or", "ag", "model", points=[(960, 428)], extra="exitX=1;exitY=0.5;entryX=0.5;entryY=0;")

p2.v("body", "Loop body · runs once for each flag · no chat history", LANE + "fillColor=#ffffff;strokeColor=#9673a6;dashed=1;", 640, 560, 620, 300)
p2.v("tc", "<b>Type Convert</b><br>item → Message", BOX + META, 30, 50, 150, 60, "body")
p2.v("ag", "<b>Agent</b> (LLM)<br>reads the flag, calls ≤ 3 tools<br>Max Iterations 4<br>Structured Response: 6 fields", BOX + LLM, 220, 40, 200, 80, "body")
p2.v("ad", "<b>Agent Decision</b> (code)<br>in: Structured Response<br>out: the decision", BOX + CODE, 450, 45, 150, 70, "body")
p2.v("crm", "<b>CRM Lookup</b><br>Tool Mode · crm_lookup", BOX + STORE, 60, 190, 150, 60, "body")
p2.v("inv", "<b>Invitee Lookup</b><br>Tool Mode · invitee_lookup", BOX + STORE, 230, 190, 150, 60, "body")
p2.v("chs", "<b>Company Search</b><br>Tool Mode · company_search", BOX + STORE, 400, 190, 190, 60, "body")
p2.e("item", "loop", "tc", "Item", style=LOOP, extra="exitX=1;exitY=0.25;entryX=0;entryY=0.5;")
p2.e("tc-ag", "tc", "ag", style=LOOP, extra=RIGHT)
p2.e("ag-ad", "ag", "ad", style=LOOP, extra=RIGHT)
p2.e("back", "ad", "loop", "Decision → Item (looping)", style=LOOP, points=[(1290, 640), (1290, 880), (580, 880), (580, 652)],
     extra="exitX=1;exitY=0.5;entryX=1;entryY=0.75;")
for tool, x in (("crm", 0.25), ("inv", 0.5), ("chs", 0.75)):
    p2.e(f"{tool}-ag", tool, "ag", "Tools" if tool == "inv" else "", style=EDGE + "strokeColor=#82b366;",
         extra=f"exitX=0.5;exitY=0;entryX={x};entryY=1;")

p2.v("p1", "<b>Part 1 RAG pipeline</b><br>ask() in the Part 1 venv (subprocess)<br>guest numbers · dietary needs<br>venue and access · data retention",
     BOX + CODE + "dashed=1;", 640, 1040, 280, 90)
p2.e("pb-p1", "pb", "p1", style=EDGE + BOTH, extra=RIGHT)
p2.v("out", "<b>outputs/</b><br>attendees.csv · audit_log.json<br>run_report.json · planner_brief.md", CYL + STORE, 640, 1150, 280, 90)
p2.e("wo-out", "wo", "out", extra=RIGHT)

p2.v("n1", "<b>Langflow 1.13 on the laptop</b>, in its own venv. Each Event AI component wraps a tested eventai "
     "module; the canvas only wires them. 16 components plus Agent Decision and Planner Brief.", NOTE, 1320, 300, 300, 100)
p2.v("n2", "<b>No input from before the Loop into its body.</b> The Loop runs its body as a sub-graph with every "
     "predecessor, so a link to Load Event re-ran the start of the flow for each flag. The tools read the event "
     "from memory instead.", NOTE, 1320, 560, 300, 120)
p2.v("n3", "<b>Why Agent Decision.</b> The Loop collects the first output of the last box in its body. The Agent's "
     "first output is its text Response. Agent Decision has one output, so the Loop collects the decision.",
     NOTE, 1320, 710, 300, 110)
p2.legend("lg", 1320, 900, [(LLM, "LLM step"), (CODE, "Code step (Event AI)"), (STORE, "Tool (reads data)"),
                            (CONTEXT, "Loop control"), (META, "Langflow core component")])


# Page 3: the agent loop for one flag (sequence from seqlayout.py)
def page3(seq_xml):
    page = re.search(r"<diagram[\s\S]*?</diagram>", seq_xml).group(0)
    page = re.sub(r'<diagram id="[^"]*"', '<diagram id="p3"', page, count=1)
    page = add_style(page, "loop", CONTEXT)
    page = add_style(page, "agent", LLM)
    page = add_style(page, "tools", STORE)
    page = add_style(page, "crm", FILE)
    page = add_style(page, "apply", CODE)
    for msg in ("m1", "m6"):  # the two model calls
        page = add_style(page, msg, "strokeColor=#9673a6;strokeWidth=2;")
    page = add_style(page, "m3", "strokeColor=#82b366;strokeWidth=2;fontStyle=1;")  # the only step that reads data
    # seqlayout's notes are 140 x 40, too small for three lines; 170 wide still clears the next activation bar.
    for note in ("note2", "note7", "note9"):
        page = re.sub(rf'(<mxCell id="{note}" [\s\S]*?<mxGeometry x="\d+" y="\d+" )width="\d+" height="\d+"',
                      r'\1width="170" height="56"', page, count=1)
        page = add_style(page, note, "fontSize=11;")
    lifeline = re.search(r'<mxCell id="loop" [\s\S]*?y="(\d+)" width="\d+" height="(\d+)"', page)
    key_y = int(lifeline.group(1)) + int(lifeline.group(2)) + 30
    extra = Page("extra")
    extra.title("t3", "Event AI · The agent loop for one flag (A06 from e10, invalid phone)", y=0, w=1000)
    extra.v("key3", "<b>The model chooses; code executes and checks.</b> For each flag, the Agent reads the record and "
            "the flag, asks for up to 3 tools, and reads each result as JSON text. Then it returns one decision: "
            "use_value, keep or human_review, with a source and a reason. Apply Decisions accepts a value only when "
            "it is in the evidence; if not, the record goes to human review. This is the loop that Part 1 does not have.",
            BOX + "align=left;spacingLeft=12;spacingRight=12;" + WHITE, 40, key_y, 900, 100)
    extra.legend("lg3", 980, key_y, [(LLM, "LLM step"), (CONTEXT, "Loop control"),
                                    (STORE, "Tool (reads data)"), (CODE, "Code check"), (FILE, "Data file")])
    return page.replace("</root>", "".join(extra.cells) + "</root>")


# Page 4: one attendee from email to output (e05 + e06)
p4 = Page("4 · One attendee, email to output")
p4.title("t", "Event AI · One attendee from email to output (e05 + e06 → A04)", w=1000)
CARD = BOX + "align=left;verticalAlign=top;spacingLeft=10;spacingRight=10;spacingTop=6;fontSize=11;"
p4.v("x5", "<b>e05 · extract</b> (work email, 3 Nov)<br>full_name: Jonathon Reed<br>email: J.Reed@Quillmere.example"
     "<br>phone: 0113 496 0461<br>company: Quillmere Events Ltd<br>dietary: <i>absent</i><br>attending: yes", CARD + LLM, 40, 80, 260, 140)
p4.v("x6", "<b>e06 · extract</b> (personal email, 5 Nov)<br>full_name: Jonathan Reed<br>email: jon.reed@mailbox.example"
     "<br>phone: <i>absent</i><br>company: Quillmere Events<br>dietary: no nuts<br>attending: yes", CARD + LLM, 40, 250, 260, 140)
p4.v("g", "<b>ground</b><br>each value is found in its own email → kept<br><br><i>A value that is not in the email "
     "is removed and gets the flag not_in_source:&lt;field&gt;.</i>", CARD + CODE, 360, 165, 260, 140)
p4.v("n", "<b>normalize</b><br>email → j.reed@quillmere.example <i>(corrected)</i><br>phone → +441134960461 "
     "<i>(corrected, E.164)</i><br>names and company suffixes in one form<br><i>Each change is an audit entry.</i>",
     CARD + CODE, 680, 165, 280, 140)
p4.v("d", "<b>dedupe</b><br>emails differ → fuzzy match:<br>name 92 · company 100 (suffix ignored)<br>→ <b>merged as A04</b><br>"
     "name: 2 values → conflict<br>email: 2 values → conflict<br>dietary: no nuts (the later email)", CARD + CODE,
     1020, 165, 280, 140)
p4.v("vf", "<b>verify</b><br>CRM C005 matches the work email<br>name conflict → the CRM confirms \"Jonathan Reed\"<br>"
     "email conflict → the CRM confirms the work email<br>invited: yes · format: valid<br>"
     "Companies House: not on the register (note)", CARD + CODE, 1020, 420, 280, 150)
p4.v("rs", "<b>Agent step</b><br>no open flags → the record skips the Loop<br><br><i>A conflict that the CRM settles is a "
     "rule, so code settles it. The Agent gets only what needs judgement.</i>", CARD + LLM + "dashed=1;",
     680, 420, 280, 150)
rows = [("full_name", "Jonathan Reed", "verified", "crm.csv#C005 · gmail:e06"),
        ("email", "j.reed@quillmere.example", "verified", "gmail:e05 · crm.csv#C005"),
        ("phone", "+441134960461", "corrected", "gmail:e05"),
        ("company", "Quillmere Events Ltd", "verified", "gmail:e05 · crm.csv#C005"),
        ("company_number", "", "absent", "note: not on the register"),
        ("dietary_needs", "no nuts", "verified", "gmail:e06"),
        ("flags", "none", "", "audit: 2 changes, 1 merge, 2 rules")]
cells = "".join(f"<tr><td><b>{f}</b></td><td>{v}</td><td>{s}</td><td>{src}</td></tr>" for f, v, s, src in rows)
table = ('<b>Output row A04</b> (attendees.csv)<table border="1" cellpadding="3" style="border-collapse:collapse;'
         'font-size:11px;margin-top:4px"><tr><th>field</th><th>value</th><th>status</th><th>source</th></tr>'
         + cells + "</table>")
p4.v("o", table, BOX + STORE + "align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;fontSize=11;", 40, 420, 580, 230)
p4.e("a1", "x5", "g", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.25;")
p4.e("a2", "x6", "g", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.75;")
p4.e("a3", "g", "n", extra=RIGHT)
p4.e("a4", "n", "d", extra=RIGHT)
p4.e("a5", "d", "vf", extra=DOWN)
p4.e("a6", "vf", "rs", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
p4.e("a7", "rs", "o", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
p4.v("st", "<b>Field status</b><br>verified: in the source and passed the checks<br>corrected: changed by a rule or a "
     "resolution (old value in the audit log)<br>absent: no source has a value (never invented)<br>"
     "conflict: sources disagree; human review", NOTE, 680, 620, 340, 110)
p4.legend("lg", 1080, 620, [(LLM, "LLM step"), (CODE, "Code step"), (STORE, "Output")])

seq_file = Path(__file__).with_name("agent-loop.drawio")
xml = mxfile(p1.xml("p1"), p2.xml("p2"), page3(seq_file.read_text()) if seq_file.exists() else "", p4.xml("p4"))
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(xml)
print(f"wrote {OUT}")
