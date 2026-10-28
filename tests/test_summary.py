"""The README summary (S2) and its PDF builder (docs/build_summary_pdf.py). No Chrome call."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_summary_pdf", ROOT / "docs" / "build_summary_pdf.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

SUMMARY = build.summary_markdown((ROOT / "README.md").read_text())
# The brief asks for the approach, the tools, the data sources, the architecture and the key reasoning steps.
SECTIONS = ["The problem", "What the system does", "Results", build.PAGE_2, "Approach and architecture",
            "Key reasoning steps", "Tools", "Data sources", "Limits and next steps"]


@pytest.mark.parametrize("heading", SECTIONS)
def test_summary_has_each_section(heading):
    assert re.search(rf"^#+ {re.escape(heading)}$", SUMMARY, re.M)


def test_summary_images_exist():
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", SUMMARY)
    assert len(images) == 2
    for path in images:
        assert (ROOT / path).is_file(), path


def test_summary_stops_at_the_marker():
    assert "Run it yourself" not in SUMMARY
    with pytest.raises(ValueError):
        build.summary_markdown("# A README with no marker")


def test_html_starts_page_2_and_keeps_the_tables():
    html = build.to_html(SUMMARY)
    assert html.count('class="page-2"') == 1
    assert html.count("<table>") == 5
    assert f'<base href="{ROOT.as_uri()}/">' in html
