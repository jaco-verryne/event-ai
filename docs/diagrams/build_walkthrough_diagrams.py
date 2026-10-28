"""Build docs/diagrams/part2-walkthrough.drawio (3 pages): Part 2 explained with one example.

    python docs/diagrams/build_walkthrough_diagrams.py docs/diagrams/part2-walkthrough.drawio

Page 1 follows one email (Sam Okoro, e10 -> A06) through every component. Page 2 shows the four paths
that an email can take. Page 3 shows where Part 1 works inside a Part 2 run. The values come from the
committed run of 28 Oct (outputs/) and its Langfuse trace.
"""

import sys
from pathlib import Path

from drawio_kit import BOX, CODE, CONTEXT, DASHED, EDGE, EXT, FILE, LLM, META, STORE, Page, mxfile

OUT = Path(sys.argv[1])
NOTE = "shape=note;whiteSpace=wrap;html=1;size=14;fontSize=11;align=left;spacingLeft=8;spacingRight=8;" + CONTEXT
WHITE = "fillColor=#ffffff;strokeColor=#666666;"
CARD = BOX + "align=left;verticalAlign=middle;spacingLeft=12;spacingRight=12;fontSize=11;" + WHITE
STATION = BOX + "align=left;spacingLeft=12;spacingRight=8;"
DOWN = "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
RIGHT = "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
AREA = "rounded=1;arcSize=3;whiteSpace=wrap;html=1;verticalAlign=top;fontStyle=1;fontSize=13;spacingTop=6;"

# Page 1: one email through every component
p1 = Page("1 · One email, step by step")
p1.title("t", "Event AI · Part 2 step by step: Sam Okoro's reply (email e10 → attendee A06)", w=1000)

steps = [
    ("<b>0 · Run command</b> (code, outside Langflow)<br>python -m eventai.agent.run", META,
     "Calendar: one upcoming event has a <i>Venue:</i> line → <b>partnersummit2026</b><br>"
     "It calls the Langflow API with that ID as the chat input, so the server traces the run.", 70),
    ("<b>1 · Load Event</b> (code)<br>Google Calendar, read-only", CODE,
     "Northern Partners Summit 2026 · Thu 26 Nov 2026, 14:00<br>Venue <b>V113</b> (Roundhay Hall) · 12 invitees, "
     "among them sam.okoro@saltmere.example", 70),
    ("<b>2 · Load RSVP Emails</b> (code)<br>Gmail search, read-only", CODE,
     "Search: \"Northern Partners Summit\" -from:me → 13 emails (15 from 29 Oct, D19)<br>"
     "<b>e10</b> · Sam Okoro · Wed 4 Nov 08:05<br><i>\"Yes, I will attend. My mobile is 0113 496 07 if you need me on "
     "the day.\"</i> · signature: Operations Manager, Saltmere Freight PLC", 90),
    ("<b>3 · Extract RSVPs</b> (LLM)<br>Groq openai/gpt-oss-120b<br>one call per email, JSON only", LLM,
     "is_rsvp: true · attending: true<br>full_name: Sam Okoro · email: sam.okoro@saltmere.example<br>"
     "phone: <b>0113 496 07</b> · company: Saltmere Freight PLC<br>job_title: Operations Manager · "
     "dietary_needs: null<br><i>Copied exactly as written. The LLM does not correct anything.</i>", 110),
    ("<b>4 · Check Records</b> (code)<br>five checks, no LLM", CODE,
     "<b>filter:</b> is_rsvp is true → kept<br><b>ground:</b> each value is in the email text → verified<br>"
     "<b>normalize:</b> 0113 496 07 has too few digits → status conflict, flag <b>phone_invalid</b><br>"
     "<b>dedupe:</b> no other email from Sam → own record; IDs follow the date of the first email → <b>A06</b><br>"
     "<b>verify:</b> CRM row C007 matches → name, email and company confirmed; the CRM phone +441134960712 "
     "goes into the phone note · on the invitee list · Companies House: not on the register (a note)<br>"
     "→ <b>review queue:</b> 1 item for Sam: A06 · phone_invalid, with his fields and his email", 150),
    ("<b>5 · Loop → Agent</b> (LLM)<br>OpenRouter Nemotron, ≤ 3 tool calls<br>tools: CRM, invitees, Companies House",
     LLM,
     "Reads: \"Record A06. Flag: phone_invalid on the field phone.\" + the fields + the email<br>"
     "Tool call: crm_lookup(\"sam.okoro@saltmere.example\") → C007 · phone +441134960712<br>"
     "Decision: <b>use_value</b> · phone · +441134960712 · source crm.csv#C007<br>"
     "Reason: \"The CRM record C007 contains a valid UK phone number …\"", 110),
    ("<b>6 · Apply Decisions</b> (code)<br>the safety net", CODE,
     "Is +441134960712 in the evidence? CRM row C007 has exactly this value → <b>accepted</b><br>"
     "phone = +441134960712 · status <b>corrected</b> · source crm.csv#C007 · note: was '0113 496 07'<br>"
     "<i>A value that is not in an email, the CRM or the invitee list goes to human review.</i>", 90),
    ("<b>7 · Planner Brief</b> (code + Part 1)<br>4 questions to Part 1's ask()", CODE,
     "Sam is 1 of 9 attending. Part 1 answers \"When are final guest numbers due …?\" with POL-GST-01:<br>"
     "\"10 working days before the event\" → code computes <b>Thu 12 Nov 2026</b><br>"
     "To do: Send the final guest numbers (9 attending) by Thu 12 Nov 2026", 90),
    ("<b>8 · Write Outputs</b> (code)<br>outputs/", STORE,
     "attendees.csv: row A06, each field with its value, status, source and note<br>"
     "audit_log.json: 3 entries for Sam (normalize: flagged · verify: note · resolve: use_value)<br>"
     "run_report.json and planner_brief.md for the whole run", 80),
    ("<b>9 · Results page</b> (Part 1 web app)<br>read-only, after commit and push", STORE,
     "Row A06 with the phone in blue (corrected). Pick A06 to see its fields and its 3 audit entries.", 60),
]
y, prev = 70, None
for i, (station, style, card, h) in enumerate(steps):
    p1.v(f"s{i}", station, STATION + style, 40, y, 330, h)
    p1.v(f"c{i}", card, CARD, 420, y, 680, h)
    p1.e(f"sc{i}", f"s{i}", f"c{i}", style=DASHED + RIGHT + "endArrow=none;")
    if prev:
        p1.e(f"d{i}", prev, f"s{i}", style=EDGE + DOWN)
    prev = f"s{i}"
    y += h + 30
p1.legend("lg", 1150, 70, [(LLM, "LLM step"), (CODE, "Code step"), (META, "Outside Langflow"),
                           (STORE, "Output")])
p1.v("n1", "<b>One email of thirteen.</b> Each step works on all the emails at once. Only the Loop goes "
     "one flag at a time.", NOTE, 1150, 220, 260, 90)
p1.v("n2", "<b>The pattern:</b> the LLM reads and proposes (steps 3 and 5). Code checks, decides and records "
     "(steps 4 and 6). Each change has an audit entry with its source.", NOTE, 1150, 340, 260, 110)
p1.v("n3", "<b>Zoom in:</b> the agent loop for this flag is the page \"3 · The agent loop for one flag\" in "
     "event-ai-part2.drawio.", NOTE, 1150, 480, 260, 80)

# Page 2: the four paths
p2 = Page("2 · Four paths for an email")
p2.title("t", "Event AI · Part 2: the four paths that an email can take", w=1000)
p2.v("inbox", "<b>Gmail inbox</b> of the demo account<br>13 RSVPs, plus 4 other emails from 28 Oct (D19)",
     BOX + META, 420, 70, 380, 60)
p2.v("load", "<b>Load RSVP Emails</b> (code)<br>search: \"Northern Partners Summit\" -from:me",
     BOX + CODE, 420, 170, 380, 60)
p2.v("out0", "<b>Never read</b> (the search does not find them)<br>e17 a venue newsletter<br>"
     "e18 an advert for \"Northern Leaders Summit 2027\"<br><i>no LLM call</i>",
     CARD.replace(WHITE, EXT), 40, 155, 320, 90)
p2.v("ext", "<b>Extract RSVPs</b> (LLM)<br>one call per email: the fields and is_rsvp", BOX + LLM, 420, 270, 380, 60)
p2.v("chk", "<b>Check Records</b> (code)<br>filter · ground · normalize · dedupe · verify", BOX + CODE, 420, 370, 380, 60)
paths = [
    ("pa", "<b>A · Not an RSVP → skipped</b> (D19)<br><br>e15 Ravi Desai: out-of-office reply<br>"
     "e16 Fenwick &amp; Rowe: catering quote<br><br><i>An audit entry and a line in the run report. Not on the "
     "list, so Ravi stays under \"no reply\".</i>", META),
    ("pb", "<b>B · Clean → on the list</b><br><br>A01 Amelia Hart<br>A02 Priya Shah: case fixed by code<br>"
     "A08 Oliver Grant: no phone (info flag only)<br>A11 Ewan Fraser: declines → attending no<br><br>"
     "<i>No flag that needs judgement, so no agent call.</i>", STORE),
    ("pc", "<b>C · Duplicates → merged by code</b><br><br>A03 Marcus Bell: e03 + e04 from one address; the later "
     "email adds \"vegetarian\"<br>A04 Jonathan Reed: e05 work + e06 personal address; the CRM settles the "
     "name and the email<br><br><i>A conflict that the CRM settles is a rule, not a judgement.</i>", CODE),
    ("pd", "<b>D · Flag → Agent → code check</b><br><br>Accepted, the value is in the CRM:<br>"
     "A05 Bob → Robert Harper (C006)<br>A06 Sam Okoro: phone (C007)<br>A07 Brightwyn Analytcs → Brightwyn "
     "Analytics Ltd (C008)<br>Human review:<br>A09 Leah Morgan: a substitute, not invited<br>"
     "A10 Chloe Adams: the reply is not clear", LLM),
]
for i, (pid, label, style) in enumerate(paths):
    p2.v(pid, label, BOX + "align=left;verticalAlign=top;spacingLeft=10;spacingRight=10;spacingTop=8;fontSize=11;"
         + style, 40 + i * 300, 490, 280, 215)
    p2.e(f"e{pid}", "chk", pid, style=EDGE + DOWN)
p2.v("wo", "<b>Apply Decisions → Write Outputs</b> (code)<br>11 attendees · 9 attending of 100 seats · 5 flagged: "
     "3 fixed, 2 to human review<br>Invited, no reply: Tom Price, Ravi Desai", BOX + STORE, 340, 760, 560, 80)
p2.e("e1", "inbox", "load", style=EDGE + DOWN)
p2.e("e2", "load", "ext", style=EDGE + DOWN)
p2.e("e3", "ext", "chk", style=EDGE + DOWN)
p2.e("e4", "load", "out0", "left out", style=DASHED + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
for pid in ("pb", "pc", "pd"):
    p2.e(f"w{pid}", pid, "wo", style=EDGE + DOWN)
p2.e("wpa", "pa", "wo", "run report only", style=DASHED + "exitX=0.5;exitY=1;entryX=0;entryY=0.5;",
     points=((180, 800),))
p2.legend("lg", 1270, 70, [(LLM, "LLM step"), (CODE, "Code step"), (STORE, "On the list"),
                           (META, "Skipped (audited)"), (EXT, "Never read")])
p2.v("n1", "<b>Who decides what is on the list?</b> Code. The LLM extracts the fields and says whether an "
     "email is an RSVP; the Agent proposes a fix for each flag. Code accepts a fix only when the value is in "
     "the evidence.", NOTE, 870, 155, 360, 100)
p2.v("n2", "<b>Numbers from the committed run</b> (28 Oct, 08:09, 13 emails). Path A starts with the run on "
     "29 Oct, after the noise emails went into the inbox.", NOTE, 870, 290, 360, 80)

# Page 3: Part 1 inside a Part 2 run
p3 = Page("3 · Where Part 1 works in Part 2")
p3.title("t", "Event AI · Where Part 1 works inside a Part 2 run", w=900)
p3.v("a2", "Part 2 run · Langflow on the laptop", AREA + "fillColor=#fbf8fc;strokeColor=#9673a6;", 40, 70, 380, 600)
p3.v("a1", "Part 1 · the same repository and eventai code", AREA + "fillColor=#f7fafd;strokeColor=#6c8ebf;",
     1000, 70, 380, 600)
p3.v("le", "<b>Load Event</b> (code)<br>the event description says \"Venue: V113\"", BOX + CODE, 70, 120, 320, 70)
p3.v("lc", "<b>Check Records</b> (code)<br>capacity check: 9 attending, 100 seats → not over", BOX + CODE,
     70, 250, 320, 70)
p3.v("lb", "<b>Planner Brief</b> (code)<br>4 questions, built from this run's data<br>Part 1 answers them with "
     "sources<br>code turns each cited rule into a date", BOX + CODE, 70, 380, 320, 100)
p3.v("lw", "<b>Write Outputs</b> (code)<br>planner_brief.md · run_report.json", BOX + STORE, 70, 560, 320, 70)
p3.v("rd", "<b>data/</b> · the Part 1 knowledge base<br>venues.csv · policies.csv · packages.json",
     BOX + FILE, 1030, 120, 320, 70)
p3.v("ra", "<b>ask(question)</b> · eventai.rag.pipeline<br>router (LLM) → query_sql / search_text (code)<br>"
     "→ answer (LLM) → citation check (code)", BOX + CODE, 1030, 380, 320, 100)
p3.v("rr", "<b>Part 2 results page</b><br>in the Part 1 web app, read-only (D6)", BOX + STORE, 1030, 560, 320, 70)
for a, b in (("le", "lc"), ("lc", "lb"), ("lb", "lw")):
    p3.e(f"{a}{b}", a, b, style=EDGE + DOWN)
p3.e("cap", "rd", "lc", "① the same data file: seated_capacity of V113 = 100 (no LLM)",
     style=EDGE + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;strokeColor=#d79b00;", points=((700, 155), (700, 285)))
p3.e("ask", "lb", "ra", "② ask() four times, in the Part 1 venv (a subprocess)",
     style=EDGE + RIGHT + "startArrow=block;startFill=1;startSize=8;strokeColor=#d79b00;")
p3.e("reads", "ra", "rd", "reads", style=EDGE + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
p3.e("pub", "lw", "rr", "③ commit and push → the page shows the run",
     style=EDGE + RIGHT + "strokeColor=#d79b00;")
table = (
    "<b>One brief question, end to end</b> (the 28 Oct run)"
    "<table style='border-collapse:collapse;margin-top:6px' border='1' cellpadding='4'>"
    "<tr><td><b>Question</b> (Part 2 code)</td><td>When are final guest numbers due for an event on 26 November "
    "2026, and what happens if guest numbers rise after that?</td></tr>"
    "<tr><td><b>Router</b> (Part 1 LLM)</td><td>SELECT policy_id, area, applies_to, condition, rule, "
    "effective_from FROM policies WHERE area = 'guest numbers'</td></tr>"
    "<tr><td><b>query_sql</b> (code)</td><td>read-only DuckDB, after the six guardrails → all the guest-number "
    "rules</td></tr>"
    "<tr><td><b>Answer</b> (Part 1 LLM)</td><td>\"Final guest numbers are due 10 working days before the 26 "
    "November 2026 event …\" · sources POL-GST-01, POL-GST-04</td></tr>"
    "<tr><td><b>Citation check</b> (code)</td><td>each source ID was in the tool results</td></tr>"
    "<tr><td><b>Date</b> (Part 2 code)</td><td>POL-GST-01 applies to all events: 10 working days before Thu 26 "
    "Nov → <b>Thu 12 Nov 2026</b> (weekends skipped). A rule for one package only (POL-GST-02, Gala Dinner) "
    "sets no date.</td></tr>"
    "<tr><td><b>To do</b></td><td>Send the final guest numbers (9 attending) by Thu 12 Nov 2026 "
    "(policies.csv#POL-GST-01)</td></tr></table><br>"
    "<b>The other three questions</b> ask about dietary needs (POL-DIE-01 → Thu 12 Nov), the venue and access "
    "(V113: step-free, in-house catering, 100 seats) and data retention (POL-DAT-02 → Sat 26 Dec)."
)
p3.v("ex", table, BOX + "align=left;verticalAlign=top;spacingLeft=10;spacingRight=10;spacingTop=8;fontSize=11;"
     + WHITE, 40, 710, 1340, 250)
p3.v("n1", "<b>Why code computes the dates:</b> an LLM is not reliable with working-day arithmetic. Part 1 "
     "finds and cites the rule; Part 2 code does the sum.", NOTE, 470, 455, 480, 70)

OUT.write_text(mxfile(p1.xml("w1"), p2.xml("w2"), p3.xml("w3")))
print(f"Wrote {OUT}")
