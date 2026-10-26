"""Build docs/diagrams/event-ai-part1.drawio (3 pages). Usage: python docs/diagrams/build_part1_diagrams.py docs/diagrams/event-ai-part1.drawio"""

import sys
from html import escape
from pathlib import Path

OUT = Path(sys.argv[1])

FILE = "fillColor=#ffe6cc;strokeColor=#d79b00;"
STORE = "fillColor=#d5e8d4;strokeColor=#82b366;"
CODE = "fillColor=#dae8fc;strokeColor=#6c8ebf;"
LLM = "fillColor=#e1d5e7;strokeColor=#9673a6;"
EXT = "fillColor=#f5f5f5;strokeColor=#666666;dashed=1;"
CONTEXT = "fillColor=#fff2cc;strokeColor=#d6b656;"
ERROR = "fillColor=#f8cecc;strokeColor=#b85450;"
META = "fillColor=#f5f5f5;strokeColor=#666666;"
BOX = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;"
LANE = "swimlane;startSize=30;html=1;rounded=1;arcSize=4;fontStyle=1;fontSize=13;container=1;pointerEvents=0;"
CYL = "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;fontSize=12;"
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;endSize=8;fontSize=11;labelBackgroundColor=#ffffff;"
DASHED = EDGE + "dashed=1;strokeColor=#7f7f7f;"


class Page:
    def __init__(self, name):
        self.name = name
        self.cells = []

    def v(self, id_, label, style, x, y, w, h, parent="1"):
        self.cells.append(
            f'<mxCell id="{id_}" value="{escape(label)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )

    def e(self, id_, src, tgt, label="", style=EDGE, points=(), extra=""):
        pts = ""
        if points:
            pts = '<Array as="points">' + "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points) + "</Array>"
        self.cells.append(
            f'<mxCell id="{id_}" value="{escape(label)}" style="{style}{extra}" edge="1" parent="1" '
            f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>'
        )

    def title(self, id_, text, x=40, y=10, w=700):
        self.v(id_, text, "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;", x, y, w, 40)

    def legend(self, id_, x, y, rows):
        h = 30 + 24 * len(rows)
        self.v(id_, "Legend", "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#666666;"
               "verticalAlign=top;fontStyle=1;container=1;pointerEvents=0;", x, y, 210, h)
        for i, (style, text) in enumerate(rows):
            self.v(f"{id_}-s{i}", "", "rounded=0;html=1;" + style, 10, 30 + 24 * i, 30, 16, parent=id_)
            self.v(f"{id_}-t{i}", text, "text;html=1;align=left;verticalAlign=middle;fontSize=11;",
                   50, 28 + 24 * i, 150, 20, parent=id_)

    def xml(self, page_id):
        body = "".join(self.cells)
        return (f'<diagram id="{page_id}" name="{escape(self.name)}"><mxGraphModel dx="1600" dy="1000" grid="1" '
                f'gridSize="10" guides="1" page="0" math="0" shadow="0"><root><mxCell id="0"/>'
                f'<mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>')


# Page 1: architecture
p1 = Page("1 · Part 1 architecture")
p1.title("t", "Event AI · Part 1 architecture (RAG chat)")
p1.v("kb", "Knowledge base files (data/)", LANE + FILE, 40, 140, 200, 300)
p1.v("f-pkg", "packages.json<br>8 packages", BOX + FILE, 20, 50, 160, 60, "kb")
p1.v("f-ven", "venues.csv<br>120 venues", BOX + FILE, 20, 130, 160, 60, "kb")
p1.v("f-pol", "policies.csv<br>26 rules", BOX + FILE, 20, 210, 160, 60, "kb")
p1.v("su", "Start-up (once per server process)", LANE + "fillColor=#ffffff;strokeColor=#82b366;", 300, 60, 340, 400)
p1.v("loader", "<b>Loader</b><br>read files once<br>build tables + chunks", BOX + CODE, 20, 180, 120, 100, "su")
p1.v("duck", "<b>DuckDB</b><br>4 tables<br>read-only", CYL + STORE, 190, 60, 130, 100, "su")
p1.v("tix", "<b>Text index</b><br>Chroma vectors<br>+ BM25", CYL + STORE, 190, 240, 130, 100, "su")
p1.v("ask", "Per question: ask()", LANE + "fillColor=#ffffff;strokeColor=#6c8ebf;", 720, 40, 480, 640)
p1.v("router", "<b>Router</b> (LLM call 1)<br>intent · tools · SQL · search words<br>standalone question", BOX + LLM, 130, 50, 220, 70, "ask")
p1.v("qsql", "<b>query_sql</b><br>6 guardrails · one repair<br>adds missing ID columns", BOX + CODE, 20, 190, 190, 90, "ask")
p1.v("stext", "<b>search_text</b><br>vectors + BM25 → RRF<br>min score 0.5", BOX + CODE, 270, 190, 190, 90, "ask")
p1.v("answer", "<b>Answer</b> (LLM call 2)<br>uses only the tool results", BOX + LLM, 130, 380, 220, 70, "ask")
p1.v("cite", "<b>Citation check</b> (code)<br>drops unknown IDs · VAT note", BOX + CODE, 130, 520, 220, 70, "ask")
p1.v("ext", "External services", LANE + EXT, 1260, 220, 200, 260)
p1.v("llm", "<b>LLM providers</b><br>Groq gpt-oss-120b (first)<br>OpenRouter free (fallback)", BOX + META, 10, 40, 180, 90, "ext")
p1.v("lf", "<b>Langfuse Cloud</b><br>one trace per question", BOX + META, 10, 160, 180, 80, "ext")
p1.v("app", "<b>Streamlit app</b><br>Chat · Knowledge base<br>(Streamlit Community Cloud)", BOX + "fillColor=#ffffff;strokeColor=#000000;", 1480, 550, 200, 90)
p1.e("e1", "kb", "loader", "read once", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p1.e("e2", "loader", "duck", extra="exitX=1;exitY=0.25;entryX=0;entryY=0.5;")
p1.e("e3", "loader", "tix", extra="exitX=1;exitY=0.75;entryX=0;entryY=0.5;")
p1.e("e4", "app", "router", "question + history", points=[(1580, 125)], extra="exitX=0.5;exitY=0;entryX=1;entryY=0.5;")
p1.e("e5", "router", "qsql", "SQL", extra="exitX=0.25;exitY=1;entryX=0.5;entryY=0;")
p1.e("e6", "router", "stext", "search words", extra="exitX=0.75;exitY=1;entryX=0.5;entryY=0;")
p1.e("e7", "qsql", "stext", "record IDs", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p1.e("e8", "qsql", "duck", "checked SELECT", points=[(670, 275), (670, 170)], extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
p1.e("e9", "stext", "tix", "", points=[(1028, 345)], extra="exitX=0.2;exitY=1;entryX=1;entryY=0.5;")
p1.e("e10", "qsql", "answer", "rows + IDs", points=[(835, 390), (905, 390)], extra="exitX=0.5;exitY=1;entryX=0.25;entryY=0;jumpStyle=arc;jumpSize=10;")
p1.e("e11", "stext", "answer", "hits", points=[(1085, 390), (1015, 390)], extra="exitX=0.5;exitY=1;entryX=0.75;entryY=0;")
p1.e("e12", "answer", "cite", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p1.e("e13", "cite", "app", "answer · facts · sources", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p1.e("e14", "router", "llm", "LLM call", style=DASHED, points=[(1220, 146), (1220, 305)], extra="exitX=1;exitY=0.8;entryX=0;entryY=0.5;")
p1.e("e15", "answer", "llm", "", style=DASHED, points=[(1235, 455), (1235, 330)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.78;")
p1.e("e16", "ask", "lf", "traces", style=DASHED, points=[(1245, 520), (1245, 420)], extra="exitX=1;exitY=0.75;entryX=0;entryY=0.5;")
p1.legend("lg", 40, 520, [(FILE, "Data file"), (STORE, "Data store / index"), (CODE, "Code step"),
                          (LLM, "LLM call"), (META, "External service")])

# Page 2: from record to chunk
p2 = Page("2 · From record to chunk")
p2.title("t", "Event AI · From record to table and chunk", w=800)
p2.v("kb", "Knowledge base files", LANE + FILE, 40, 60, 200, 380)
p2.v("f-ven", "venues.csv<br>120 rows", BOX + FILE, 20, 50, 160, 60, "kb")
p2.v("f-pkg", "packages.json<br>8 objects, nested lists", BOX + FILE, 20, 160, 160, 60, "kb")
p2.v("f-pol", "policies.csv<br>26 rows", BOX + FILE, 20, 290, 160, 60, "kb")
p2.v("db", "DuckDB tables (attribute fields → SQL)", LANE + "fillColor=#ffffff;strokeColor=#82b366;", 310, 60, 250, 380)
p2.v("t-ven", "<b>venues</b> · 120 rows", BOX + STORE, 20, 50, 210, 60, "db")
p2.v("t-pkg", "<b>packages</b> · 8 rows<br>suitable_venue_types = list", BOX + STORE, 20, 130, 210, 60, "db")
p2.v("t-itm", "<b>package_items</b> · 73 rows<br>included items + add-ons", BOX + STORE, 20, 210, 210, 60, "db")
p2.v("t-pol", "<b>policies</b> · 26 rows", BOX + STORE, 20, 290, 210, 60, "db")
p2.v("qsql", "<b>query_sql</b><br>filters · counts · joins<br>on typed columns", BOX + CODE, 640, 210, 200, 80)
p2.v("note", "Numbers are not embedded:<br>a vector cannot compare 150 with 120.<br>They stay SQL filters.", "shape=note;whiteSpace=wrap;html=1;size=14;fontSize=11;" + CONTEXT, 640, 320, 240, 70)
p2.v("builder", "<b>Chunk builder</b><br>one chunk per record<br>154 chunks · nothing cut · no overlap", BOX + CODE, 310, 590, 250, 100)
p2.v("chunk", "One chunk · example venues.csv#V012 (row 12)", LANE + "fillColor=#ffffff;strokeColor=#6c8ebf;", 640, 500, 520, 400)
p2.v("emb", "<b>Embedding text</b> (text fields only)<br><i>The Old Mill. Converted mill. Converted Victorian mill with exposed brick and a courtyard.</i>", BOX + CODE, 20, 40, 480, 70, "chunk")
p2.v("ctx", "<b>Context text</b> (full record, with units)<br>Venue: The Old Mill (Leeds)<br>Seated capacity: 120 guests<br>Day rate: £2,400 (without VAT)<br>Parking spaces: 20 · Step-free access: yes …", BOX + CONTEXT + "align=left;spacingLeft=10;", 20, 130, 480, 140, "chunk")
p2.v("meta", "<b>Metadata</b><br>document: venues · record_id: V012 · city: Leeds · seated_capacity: 120 …", BOX + META, 20, 290, 480, 80, "chunk")
p2.v("chroma", "<b>Chroma</b><br>vectors (bge-small, local)", BOX + STORE, 1240, 500, 200, 60)
p2.v("bm25", "<b>BM25 index</b><br>record ID + text fields", BOX + STORE, 1240, 580, 200, 60)
p2.v("ans", "<b>Answer step</b> (LLM)<br>reads the context text", BOX + LLM, 1240, 670, 200, 60)
p2.v("filt", "<b>Search filters</b><br>document · record_id", BOX + CODE, 1240, 800, 200, 60)
p2.e("e1", "f-ven", "t-ven", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p2.e("e2", "f-pkg", "t-pkg", extra="exitX=1;exitY=0.35;entryX=0;entryY=0.5;")
p2.e("e3", "f-pkg", "t-itm", "flattened", extra="exitX=1;exitY=0.75;entryX=0;entryY=0.5;")
p2.e("e4", "f-pol", "t-pol", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p2.e("e5", "db", "qsql", "SQL", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p2.e("e6", "kb", "builder", "same records", points=[(140, 640)], extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
p2.e("e7", "builder", "chunk", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.35;")
p2.e("e8", "emb", "chroma", "embed", extra="exitX=1;exitY=0.3;entryX=0;entryY=0.5;")
p2.e("e9", "emb", "bm25", "index", extra="exitX=1;exitY=0.8;entryX=0;entryY=0.5;")
p2.e("e10", "ctx", "ans", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p2.e("e11", "meta", "filt", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p2.legend("lg", 40, 740, [(FILE, "Data file"), (STORE, "Table / index"), (CODE, "Code step / text"),
                          (CONTEXT, "Text for the answer"), (LLM, "LLM call")])

# Page 3: one question
p3 = Page("3 · One question, step by step")
p3.title("t", "Event AI · One question, step by step", w=800)
p3.v("start", "<b>Question + chat history</b><br>each earlier answer carries its plan (question + SQL)", "ellipse;whiteSpace=wrap;html=1;fontSize=12;" + STORE, 340, 60, 320, 80)
p3.v("router", "<b>Router</b> · LLM call 1<br>intent · tools · documents · SQL · search words · standalone question", BOX + LLM, 340, 180, 320, 70)
p3.v("scope", "Out of scope?", "rhombus;whiteSpace=wrap;html=1;fontSize=12;" + CONTEXT, 420, 290, 160, 80)
p3.v("fixed", "<b>Fixed reply</b><br>no second LLM call", BOX + META, 700, 300, 180, 60)
p3.v("run", "Run the planned tools", BOX + "fillColor=#ffffff;strokeColor=#000000;", 380, 410, 240, 40)
p3.v("gr", "query_sql guardrails", LANE + "fillColor=#ffffff;strokeColor=#6c8ebf;", 80, 500, 380, 420)
gsteps = [
    ("g1", "Parse with sqlglot: one statement, SELECT only  [rule 2]"),
    ("g2", "Known tables and columns only, no table functions  [rule 3]"),
    ("g3", "Add missing ID columns, so each row can be cited"),
    ("g4", "Wrap with LIMIT 201, keep 200 rows  [rule 4]"),
    ("g5", "Run read-only, no file access, 5 s timeout  [rules 1, 5]"),
]
for i, (gid, text) in enumerate(gsteps):
    p3.v(gid, text, BOX + CODE, 20, 45 + 60 * i, 340, 40, "gr")
p3.v("g6", "<b>On error:</b> one LLM repair, then all rules again  [rule 6]<br>Second error → fixed \"cannot answer\"", BOX + ERROR, 20, 350, 340, 50, "gr")
for i in range(4):
    p3.e(f"ge{i}", gsteps[i][0], gsteps[i + 1][0], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("ge-err", "g5", "g6", "", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("ge-rep", "g6", "g1", "repaired SQL", style=DASHED + "strokeColor=#b85450;", points=[(60, 875), (60, 565)], extra="exitX=0;exitY=0.5;entryX=0;entryY=0.5;")
p3.v("stext", "<b>search_text</b><br>Chroma vectors + BM25 → RRF · top 5<br>only the rows that the SQL returned · min score 0.5", BOX + CODE, 560, 560, 320, 90)
p3.v("answer", "<b>Answer</b> · LLM call 2<br>only the tool results · each fact cites a source ID", BOX + LLM, 340, 980, 320, 70)
p3.v("cite", "<b>Citation check</b> (code)<br>drop facts with unknown IDs · add the VAT note", BOX + CODE, 340, 1090, 320, 70)
p3.v("end", "<b>Chat</b>: answer · facts · Sources · Debug<br>+ one Langfuse trace", "ellipse;whiteSpace=wrap;html=1;fontSize=12;" + STORE, 340, 1200, 320, 80)
p3.e("s1", "start", "router", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("s2", "router", "scope", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("s3", "scope", "fixed", "Yes", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
p3.e("s4", "scope", "run", "No", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("s5", "run", "gr", "SQL planned", extra="exitX=0.25;exitY=1;entryX=0.5;entryY=0;")
p3.e("s6", "run", "stext", "search planned", extra="exitX=0.75;exitY=1;entryX=0.5;entryY=0;")
p3.e("s7", "g5", "stext", "record IDs", extra="exitX=1;exitY=0.3;entryX=0;entryY=0.5;")
p3.e("s8", "gr", "answer", "rows + source IDs", points=[(270, 950), (420, 950)], extra="exitX=0.5;exitY=1;entryX=0.25;entryY=0;")
p3.e("s9", "stext", "answer", "hits + record text", points=[(720, 950), (580, 950)], extra="exitX=0.5;exitY=1;entryX=0.75;entryY=0;")
p3.e("s10", "answer", "cite", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("s11", "cite", "end", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
p3.e("s12", "fixed", "end", "", points=[(940, 330), (940, 1240)], extra="exitX=1;exitY=0.5;entryX=1;entryY=0.5;")
p3.legend("lg", 700, 1040, [(LLM, "LLM call"), (CODE, "Code step"), (ERROR, "Error path"), (META, "Fixed reply")])

xml = ('<?xml version="1.0" encoding="UTF-8"?><mxfile host="drawio" version="26.0.0">'
       + p1.xml("p1") + p2.xml("p2") + p3.xml("p3") + "</mxfile>")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(xml)
print(f"wrote {OUT}")
