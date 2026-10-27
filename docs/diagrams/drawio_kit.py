"""Shared styles and helpers for the draw.io builders, so Part 1 and Part 2 look the same."""

import re
from html import escape

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


def add_style(xml, cell_id, extra):
    """Append style keys to one cell of a page made by seqlayout.py."""
    return re.sub(rf'(<mxCell id="{cell_id}" [^>]*?style=")([^"]*)(")',
                  lambda m: m.group(1) + m.group(2) + extra + m.group(3), xml, count=1)


def mxfile(*pages):
    return '<?xml version="1.0" encoding="UTF-8"?><mxfile host="drawio" version="26.0.0">' + "".join(pages) + "</mxfile>"
