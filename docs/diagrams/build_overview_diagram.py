"""Build docs/diagrams/event-ai-overview.drawio: how Part 1 and Part 2 connect (connected but distinct).

    python docs/diagrams/build_overview_diagram.py docs/diagrams/event-ai-overview.drawio
"""

import sys
from pathlib import Path

from drawio_kit import BOX, CODE, CONTEXT, EDGE, FILE, LANE, LLM, META, STORE, Page, mxfile

OUT = Path(sys.argv[1])
NOTE = "shape=note;whiteSpace=wrap;html=1;size=14;fontSize=12;align=left;spacingLeft=10;spacingRight=10;" + CONTEXT
WHITE = "fillColor=#ffffff;strokeColor=#000000;"
DOWN = "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
BRIDGE = EDGE + "strokeWidth=2;strokeColor=#d79b00;fontStyle=1;"
BOTH = "startArrow=block;startFill=1;startSize=8;"

p = Page("Part 1 and Part 2")
p.title("t", "Event AI · How Part 1 and Part 2 connect (connected but distinct)", w=1000)

# Part 1: the website. Boxes leave a channel on the left for the question edge.
p.v("p1", "Part 1 · RAG app · Streamlit Community Cloud (public link)", LANE + "fillColor=#ffffff;strokeColor=#6c8ebf;",
    40, 70, 520, 550)
p.v("user", "<b>Reviewer or planner</b> · a browser, no sign-in", BOX + META, 40, 45, 460, 50, "p1")
p.v("pages", "<b>Chat page</b> · <b>Knowledge base page</b>", BOX + WHITE, 40, 120, 460, 60, "p1")
p.v("data", "<b>data/</b> · the knowledge base<br>packages.json · venues.csv · policies.csv<br>DuckDB tables and a Chroma + BM25 index, built at start-up",
    BOX + FILE, 40, 210, 460, 80, "p1")
p.v("ask", "<b>ask(question, history)</b> · eventai.rag.pipeline<br>router (LLM) → query_sql (DuckDB) and/or search_text<br>"
    "→ answer (LLM) → citation check (code)", BOX + CODE, 40, 320, 460, 100, "p1")
p.v("res", "<b>Part 2 results page</b> (read-only, same app)<br>attendees · flags · agent decisions · planner brief · CSV",
    BOX + WHITE, 40, 460, 460, 70, "p1")
p.e("u-pg", "user", "pages", extra=DOWN)
p.e("pg-ask", "pages", "ask", "", points=[(60, 220), (60, 440)], extra="exitX=0;exitY=0.5;entryX=0;entryY=0.5;")
p.e("ask-data", "ask", "data", "reads", extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")

# Part 2: the agent on the laptop.
p.v("p2", "Part 2 · attendee-list agent · Langflow on the laptop", LANE + "fillColor=#ffffff;strokeColor=#9673a6;",
    880, 70, 520, 550)
p.v("trig", "<b>Planner starts a run</b> · Langflow Playground: partnersummit2026", BOX + META, 20, 45, 480, 50, "p2")
p.v("goog", "<b>Google Calendar + Gmail</b> (demo account, read-only)<br>event · invitees · venue ID V113 · 13 RSVP emails",
    BOX + META, 20, 120, 480, 60, "p2")
p.v("flow", "<b>Extract RSVPs</b> (LLM) → <b>Check Records</b> (code)<br>→ <b>Loop: Agent</b> with 3 read-only tools (LLM)<br>"
    "→ <b>Apply Decisions</b> (code)", BOX + LLM, 20, 210, 480, 80, "p2")
p.v("brief", "<b>Planner Brief</b> (code)<br>asks Part 1 four questions about this event<br>code computes the dates from the cited rules",
    BOX + CODE, 20, 330, 480, 80, "p2")
p.v("wout", "<b>Write Outputs</b> → outputs/ (committed)<br>attendees.csv · audit_log.json · run_report.json · planner_brief.md",
    BOX + STORE, 20, 460, 480, 70, "p2")
for a, b in [("trig", "goog"), ("goog", "flow"), ("flow", "brief"), ("brief", "wout")]:
    p.e(f"{a}-{b}", a, b, extra=DOWN)

# The three bridges. Each is a straight line, because the boxes they join are level.
p.e("b1", "data", "flow", "① venue capacity<br>Check Records reads venues.csv#V113", style=BRIDGE,
    extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p.e("b2", "brief", "ask", "② ask() in the Part 1 venv (subprocess)<br>4 questions → cited answers", style=BRIDGE + BOTH,
    extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
p.e("b3", "wout", "res", "③ git push → results page (D6)", style=BRIDGE,
    extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")

# Shared by both parts.
p.v("sh", "Shared · one repository", LANE + "fillColor=#ffffff;strokeColor=#666666;", 40, 660, 1360, 130)
p.v("pkg", "<b>eventai package</b><br>rag/ (Part 1) · agent/ (Part 2)<br>llm.py: provider order (D15) · config.py",
    BOX + CODE, 20, 40, 420, 70, "sh")
p.v("lf", "<b>Langfuse Cloud</b> · one project<br>Part 1: a trace for each question<br>Part 2: a trace for each run; the brief shares its session ID",
    BOX + META, 470, 40, 420, 70, "sh")
p.v("ev", "<b>Tests and scores</b><br>pytest (276 tests, offline)<br>eval/run_part1.py · eval/run_part2.py", BOX + CODE, 920, 40, 420, 70, "sh")

p.v("n1", "<b>Connected:</b> one client (the event company), one event at Part 1 venue V113, one code base, "
    "one Langfuse project, and one web app that shows the results of both parts.", NOTE, 40, 820, 660, 80)
p.v("n2", "<b>Distinct:</b> Part 1 runs in the cloud for anyone; Part 2 runs on the laptop with the Google demo "
    "account. Each has its own venv (Langflow pins older duckdb, pydantic and langfuse). Part 1 never calls Part 2. "
    "Part 2 reaches Part 1 only through ask(), the same function the website uses.", NOTE, 740, 820, 660, 80)
p.legend("lg", 1440, 70, [(FILE, "Data file"), (STORE, "Output files"), (CODE, "Code step"), (LLM, "LLM step"),
                          (META, "Person or service"), ("strokeColor=#d79b00;fillColor=#ffffff;strokeWidth=2;", "Link between the parts")])

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(mxfile(p.xml("overview")))
print(f"wrote {OUT}")
