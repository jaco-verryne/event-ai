"""Score the last Part 2 run against seed/expected_attendees.csv (CLAUDE.md 10.7). No LLM call.

    python eval/run_part2.py                       # reads outputs/attendees.csv
    python eval/run_part2.py --outputs other/dir

Metrics:
- flag precision and recall over (record, flag) pairs; tool failures (web_check_failed) are counted apart,
  because a missing API key is not a data defect
- field accuracy: the final value of each field, after the agent step
- deduplication: the expected groups of emails that the run merged exactly
- resolution accuracy: the expected "<flag>:<action>" decisions that the run made

Writes eval/results/<date>_part2.json.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so that "python eval/run_part2.py" finds the eventai package

from eventai.agent.checks import TOOL_FLAGS  # noqa: E402
from eventai.agent.output import read_rows  # noqa: E402

EXPECTED = ROOT / "seed" / "expected_attendees.csv"
OUTPUTS = ROOT / "outputs"
RESULTS = ROOT / "eval" / "results"
SCORED_FIELDS = ("full_name", "email", "phone", "company", "job_title", "dietary_needs", "attending")


def split(cell: str) -> list[str]:
    return [part for part in (cell or "").split(";") if part]


def same_value(field: str, expected: str, actual: str) -> bool:
    # Exact, so a missed normalization counts as an error; an email address is case-insensitive.
    return expected.casefold() == actual.casefold() if field == "email" else expected == actual


def ratio(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 1.0


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--outputs", type=Path, default=OUTPUTS, help="folder with attendees.csv")
    parser.add_argument("--expected", type=Path, default=EXPECTED)
    parser.add_argument("--no-save", action="store_true", help="print the scores only (for a smoke test)")
    args = parser.parse_args()

    report = score(read_rows(args.expected), read_rows(args.outputs / "attendees.csv"))
    run_report = args.outputs / "run_report.json"
    if run_report.exists():
        report["run"] = json.loads(run_report.read_text())
    f, fl, d, r = report["flags"], report["fields"], report["deduplication"], report["resolutions"]
    print(f"Flags        precision {f['precision']:.0%}  recall {f['recall']:.0%}  "
          f"(TP {f['true_positives']}, FP {f['false_positives']}, FN {f['false_negatives']}; "
          f"tool-failure flags {f['tool_failure_flags']})")
    print(f"Fields       accuracy {fl['accuracy']:.0%}  ({fl['correct']} of {fl['total']})")
    print(f"Merges       {d['exact_groups']} of {d['expected_groups']} expected records exact; "
          f"{d['output_records']} records in the output")
    print(f"Resolutions  accuracy {r['accuracy']:.0%}  ({r['correct']} of {r['total']})")
    for miss in f["misses"] + fl["misses"] + r["misses"]:
        print("  miss:", miss)
    if not args.no_save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = RESULTS / f"{date.today().isoformat()}_part2.json"
        out.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
