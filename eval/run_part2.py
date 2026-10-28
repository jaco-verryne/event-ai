"""Score the last Part 2 run against seed/expected_attendees.csv (CLAUDE.md 10.7). No LLM call.

    python eval/run_part2.py                       # reads outputs/attendees.csv
    python eval/run_part2.py --outputs other/dir

Metrics:
- flag precision and recall over (record, flag) pairs; tool failures (web_check_failed) are counted apart,
  because a missing API key is not a data defect
- field accuracy: the final value of each field, after the agent step
- deduplication: the expected groups of emails that the run merged exactly
- resolution accuracy: the expected "<flag>:<action>" decisions that the run made
- planner brief: the expected Part 1 sources that the brief cites, and its deadlines
- inbox noise (D19): the emails in seed/noise_emails.yaml stay off the list, and no RSVP is skipped

A late RSVP (seed/late_rsvp.yaml, the watcher demo of D18) is in the inbox only after the demo, so its
expected row (seed/expected_late.csv) counts only when the run has that email.

Writes eval/results/<date>_part2.json.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so that "python eval/run_part2.py" finds the eventai package

from eventai.agent.checks import TOOL_FLAGS  # noqa: E402
from eventai.agent.output import read_rows  # noqa: E402

EXPECTED = ROOT / "seed" / "expected_attendees.csv"
EXPECTED_LATE = ROOT / "seed" / "expected_late.csv"
NOISE = ROOT / "seed" / "noise_emails.yaml"
OUTPUTS = ROOT / "outputs"
RESULTS = ROOT / "eval" / "results"
SCORED_FIELDS = ("full_name", "email", "phone", "company", "job_title", "dietary_needs", "attending")
# The planner brief (D17) should cite these sources from Part 1's knowledge base.
BRIEF_SOURCES = {"policies.csv#POL-GST-01", "policies.csv#POL-DIE-01", "policies.csv#POL-DAT-02", "venues.csv#V113"}


def split(cell: str) -> list[str]:
    return [part for part in (cell or "").split(";") if part]


def same_value(field: str, expected: str, actual: str) -> bool:
    # Exact, so a missed normalization counts as an error; an email address is case-insensitive.
    return expected.casefold() == actual.casefold() if field == "email" else expected == actual


def ratio(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 1.0


def with_late_rows(expected_rows: list[dict], late_rows: list[dict], output_rows: list[dict]) -> list[dict]:
    """Add the expected row of each late RSVP that the run read."""
    keys = {k for r in output_rows for k in split(r["source_keys"])}
    return expected_rows + [r for r in late_rows if set(split(r["source_keys"])) <= keys]


def score(expected_rows: list[dict], output_rows: list[dict]) -> dict:
    expected = {frozenset(split(r["source_keys"])): r for r in expected_rows}
    output = {frozenset(split(r["source_keys"])): r for r in output_rows}
    matched = sorted(expected.keys() & output.keys(), key=sorted)

    tp = fp = fn = tool_flags = 0
    flag_misses = []
    for keys in sorted(expected.keys() | output.keys(), key=sorted):
        want = set(split(expected[keys]["flags"])) if keys in expected else set()
        got_all = set(split(output[keys]["flags"])) if keys in output else set()
        tool_flags += len(got_all & TOOL_FLAGS)
        got = got_all - TOOL_FLAGS
        tp, fp, fn = tp + len(want & got), fp + len(got - want), fn + len(want - got)
        if want != got:
            flag_misses.append({"source_keys": ";".join(sorted(keys)), "missed": sorted(want - got),
                                "extra": sorted(got - want)})

    correct = 0
    field_misses = []
    for keys in matched:
        for field in SCORED_FIELDS:
            want, got = expected[keys][field], output[keys][field]
            if same_value(field, want, got):
                correct += 1
            else:
                field_misses.append({"source_keys": ";".join(sorted(keys)), "field": field,
                                     "expected": want, "actual": got})
    field_total = len(matched) * len(SCORED_FIELDS)

    resolution_total = resolution_ok = 0
    resolution_misses = []
    for keys in matched:
        want = set(split(expected[keys]["resolution"]))
        got = set(split(output[keys]["resolution"]))
        resolution_total += len(want)
        resolution_ok += len(want & got)
        if want != got:
            resolution_misses.append({"source_keys": ";".join(sorted(keys)), "expected": sorted(want),
                                      "actual": sorted(got)})

    return {
        "flags": {"precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn), "true_positives": tp,
                  "false_positives": fp, "false_negatives": fn, "tool_failure_flags": tool_flags,
                  "misses": flag_misses},
        "fields": {"accuracy": ratio(correct, field_total), "correct": correct, "total": field_total,
                   "misses": field_misses},
        "deduplication": {"expected_groups": len(expected), "exact_groups": len(matched),
                          "output_records": len(output),
                          "wrong_groups": [";".join(sorted(k)) for k in sorted(output.keys() - expected.keys(),
                                                                                  key=sorted)]},
        "resolutions": {"accuracy": ratio(resolution_ok, resolution_total), "correct": resolution_ok,
                        "total": resolution_total, "misses": resolution_misses},
    }


def score_brief(brief: dict | None) -> dict:
    if not brief or "answers" not in brief:
        return {"ran": False, "error": (brief or {}).get("error")}
    cited = {s for a in brief["answers"] for s in a["source_ids"]}
    return {"ran": True, "answers": len(brief["answers"]), "expected_sources_cited": sorted(BRIEF_SOURCES & cited),
            "expected_sources_missed": sorted(BRIEF_SOURCES - cited),
            "deadlines": [f"{d['policy_id']} {d['date']}" for d in brief["deadlines"]]}


def score_not_rsvp(noise: list[dict], run_report: dict, output_rows: list[dict]) -> dict:
    """The noise emails that the run read must be skipped, not listed; a skipped email that is not noise
    is an RSVP lost by mistake. A run from before D19 has no not_rsvp in its report, so it is not scored."""
    if "not_rsvp" not in run_report:
        return {"ran": False}
    expect = {n["key"]: n["expect"] for n in noise}
    skipped = {s["email_key"] for s in run_report["not_rsvp"]}
    listed = {k for r in output_rows for k in split(r["source_keys"])}
    read = (skipped | listed | set(run_report.get("extraction_failed") or [])) & expect.keys()
    return {"ran": True, "read": sorted(read), "kept_out": sorted(skipped & expect.keys()),
            "in_list": sorted(listed & expect.keys()), "dropped_by_mistake": sorted(skipped - expect.keys()),
            "found_in_error": sorted(k for k in read if expect[k] == "not_found")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--outputs", type=Path, default=OUTPUTS, help="folder with attendees.csv")
    parser.add_argument("--expected", type=Path, default=EXPECTED)
    parser.add_argument("--no-save", action="store_true", help="print the scores only (for a smoke test)")
    args = parser.parse_args()

    output_rows = read_rows(args.outputs / "attendees.csv")
    late_rows = read_rows(EXPECTED_LATE) if EXPECTED_LATE.exists() else []
    report = score(with_late_rows(read_rows(args.expected), late_rows, output_rows), output_rows)
    run_report = args.outputs / "run_report.json"
    if run_report.exists():
        report["run"] = json.loads(run_report.read_text())
        report["brief"] = score_brief(report["run"].get("brief"))
        noise = yaml.safe_load(NOISE.read_text()) if NOISE.exists() else []
        report["not_rsvp"] = score_not_rsvp(noise, report["run"], output_rows)
    f, fl, d, r = report["flags"], report["fields"], report["deduplication"], report["resolutions"]
    print(f"Flags        precision {f['precision']:.0%}  recall {f['recall']:.0%}  "
          f"(TP {f['true_positives']}, FP {f['false_positives']}, FN {f['false_negatives']}; "
          f"tool-failure flags {f['tool_failure_flags']})")
    print(f"Fields       accuracy {fl['accuracy']:.0%}  ({fl['correct']} of {fl['total']})")
    print(f"Merges       {d['exact_groups']} of {d['expected_groups']} expected records exact; "
          f"{d['output_records']} records in the output")
    print(f"Resolutions  accuracy {r['accuracy']:.0%}  ({r['correct']} of {r['total']})")
    b = report.get("brief", {})
    if b.get("ran"):
        print(f"Brief        {len(b['expected_sources_cited'])} of {len(BRIEF_SOURCES)} expected sources cited; "
              f"deadlines {', '.join(b['deadlines']) or 'none'}")
    n = report.get("not_rsvp", {})
    if n.get("ran"):
        print(f"Not RSVPs    {len(n['kept_out'])} of {len(n['read'])} noise emails kept out; "
              f"in the list: {', '.join(n['in_list']) or 'none'}; "
              f"RSVPs skipped by mistake: {', '.join(n['dropped_by_mistake']) or 'none'}")
    for miss in f["misses"] + fl["misses"] + r["misses"]:
        print("  miss:", miss)
    if not args.no_save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = RESULTS / f"{date.today().isoformat()}_part2.json"
        out.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
