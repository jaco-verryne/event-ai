"""Langflow component: outputs/attendees.csv, audit_log.json and run_report.json (step 9)."""

from lfx.custom import Component
from lfx.io import HandleInput, Output, StrInput
from lfx.schema import Message

from eventai.agent.output import write_outputs
from eventai.agent.schema import Attendee, AuditEntry
from eventai.config import ROOT


class WriteOutputs(Component):
    display_name = "Write Outputs"
    description = "Writes the attendee list with a status and a source for each field, the audit log and the run report."
    icon = "save"
    name = "WriteOutputs"

    inputs = [
        HandleInput(name="final", display_name="Final records", input_types=["Data", "JSON"], required=True),
        StrInput(name="out_dir", display_name="Output folder", value=str(ROOT / "outputs"), advanced=True),
    ]
    outputs = [Output(name="summary", display_name="Summary", method="write")]

    def write(self) -> Message:
        payload = self.final.data
        attendees = [Attendee.model_validate(a) for a in payload["attendees"]]
        audit = [AuditEntry.model_validate(x) for x in payload["audit"]]
        report = payload["report"]
        paths = write_outputs(self.out_dir, attendees, audit, report)
        lines = [
            f"{report['emails']} emails -> {len(attendees)} attendees ({report['merged_emails']} merged).",
            f"Flagged for review: {', '.join(report['for_review']) or 'none'}.",
            f"Resolutions: {report.get('resolutions', {})}.",
            f"Capacity: {report['capacity']['attending']} attending, {report['capacity']['seated_capacity']} seats.",
            f"No reply: {', '.join(report['no_reply']) or 'none'}.",
            f"Wrote {paths['attendees'].parent}.",
        ]
        return Message(text="\n".join(lines))
