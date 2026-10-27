"""Part 2 outputs: attendees.csv (value, status, source and note for each field), audit_log.json and
run_report.json. The read-only results page and eval/run_part2.py read these files."""

import csv
import json
from pathlib import Path

from eventai.agent.schema import FIELDS, Attendee, AuditEntry

ATTENDEE_COLUMNS = (
    ["attendee_id", "source_keys"]
    + [f"{field}{part}" for field in FIELDS for part in ("", "_status", "_source", "_note")]
    + ["flags", "resolution", "crm_id"]
)


def attendee_row(attendee: Attendee) -> dict[str, str]:
    row = {
        "attendee_id": attendee.attendee_id,
        "source_keys": ";".join(attendee.source_keys),
        "flags": ";".join(attendee.flags),
        "resolution": ";".join(attendee.resolutions),
        "crm_id": attendee.crm_id or "",
    }
    for field in FIELDS:
        fv = attendee.field(field)
        row[field] = fv.value or ""
        row[f"{field}_status"] = fv.status
        row[f"{field}_source"] = fv.source
        row[f"{field}_note"] = fv.note or ""
    return row


def write_outputs(out_dir: str | Path, attendees: list[Attendee], audit: list[AuditEntry],
                  report: dict) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {"attendees": out / "attendees.csv", "audit": out / "audit_log.json", "report": out / "run_report.json"}
    with paths["attendees"].open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ATTENDEE_COLUMNS)
        writer.writeheader()
        writer.writerows(attendee_row(a) for a in attendees)
    paths["audit"].write_text(json.dumps([e.model_dump(exclude_none=True) for e in audit], indent=2) + "\n")
    paths["report"].write_text(json.dumps(report, indent=2, default=str) + "\n")
    return paths


def read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))
