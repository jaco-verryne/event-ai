"""Build docs/Event-AI-technical-summary.pdf from the summary part of README.md (S2).

    python docs/build_summary_pdf.py

The PDF holds the README up to the marker <!-- end of summary -->, so the PDF and the GitHub page show the same text.
markdown-it-py (installed with Streamlit) makes the HTML, and headless Google Chrome prints it.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OUT = ROOT / "docs" / "Event-AI-technical-summary.pdf"
MARKER = "<!-- end of summary -->"
PAGE_2 = "How it works (for technical readers)"  # page 1 is for business readers, page 2 for technical readers
CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]

CSS = """
@page { size: A4; margin: 10mm 12mm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 8.4pt; line-height: 1.26;
       color: #1a1a1a; margin: 0; }
h1 { font-size: 15pt; margin: 0 0 3pt; }
h2 { font-size: 10.5pt; margin: 7pt 0 2pt; padding-bottom: 1pt; border-bottom: 1px solid #c8c8c8; }
h3 { font-size: 9.2pt; margin: 5pt 0 1pt; }
p { margin: 2pt 0; }
ul, ol { margin: 1pt 0; padding-left: 13pt; }
li { margin: 0.5pt 0; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0; font-size: 7.8pt; break-inside: avoid; }
th, td { border: 1px solid #c8c8c8; padding: 1.2pt 3.5pt; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
code { font-family: Menlo, monospace; font-size: 7.6pt; }
img { display: block; width: 100%; margin: 3pt auto; }
img[alt="How Part 1 and Part 2 connect"] { width: 90%; }
img[alt="Part 2 architecture"] { width: 68%; }
a { color: #1a56a0; text-decoration: none; }
.page-2 { break-before: page; }
"""


def summary_markdown(text: str) -> str:
    """The README up to the marker: the part that goes into the PDF."""
    head, found, _ = text.partition(MARKER)
    if not found:
        raise ValueError(f"README.md has no {MARKER} marker")
    return head


def to_html(markdown: str) -> str:
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(markdown)
    body = body.replace(f"<h2>{PAGE_2}</h2>", f'<h2 class="page-2">{PAGE_2}</h2>', 1)
    # The base makes the relative image paths of the README work from a temporary file.
    return (f'<!doctype html><html><head><meta charset="utf-8"><base href="{ROOT.as_uri()}/">'
            f"<title>Event AI: technical summary</title><style>{CSS}</style></head><body>{body}</body></html>")


def find_chrome() -> str:
    for name in CHROME:
        path = name if Path(name).exists() else shutil.which(name)
        if path:
            return path
    raise SystemExit("Google Chrome not found: install it, or add its path to CHROME")


def page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def main() -> None:
    html = to_html(summary_markdown(README.read_text()))
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "summary.html"
        page.write_text(html)
        subprocess.run([find_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT}", page.as_uri()], check=True, capture_output=True, timeout=120)
    print(f"wrote {OUT.relative_to(ROOT)}: {page_count(OUT.read_bytes())} pages")


if __name__ == "__main__":
    main()
