"""Langflow component: the code check of the agent's decisions (D12). A value must be in the evidence;
a missing or invalid decision sends the record to human review."""

from collections import Counter

from lfx.custom import Component
from lfx.io import HandleInput, Output
from lfx.schema import Data
from pydantic import ValidationError

from eventai.agent.flow_io import records
from eventai.agent.review import Decision, apply_decisions
from eventai.agent.schema import Attendee, Email, Event
from eventai.agent.tools import seed_files


class ApplyDecisions(Component):
    display_name = "Apply Decisions"
    description = "Applies each agent decision that passes the code check. Every other flag goes to human review."
    icon = "list-checks"
    name = "ApplyDecisions"

    inputs = [
        HandleInput(name="checked", display_name="Checked records", input_types=["Data", "JSON"], required=True),
        HandleInput(name="decisions", display_name="Decisions", input_types=["DataFrame", "Table", "Data", "JSON"],
                    required=False, info="Connect the Loop's Done output."),
    ]
    outputs = [Output(name="final", display_name="Final records", method="apply")]

    def apply(self) -> Data:
        payload = self.checked.data
        decisions, rejected = [], []
        for row in records(self.decisions):
            try:
                decisions.append(Decision.model_validate(row))
            except ValidationError:
                rejected.append(str(row)[:300])  # for example an agent error instead of a decision
        attendees, audit = apply_decisions(
            [Attendee.model_validate(a) for a in payload["attendees"]], decisions,
            emails=[Email.model_validate(e) for e in payload["emails"]], crm=seed_files.load_crm(),
            event=Event.model_validate(payload["event"]))
        actions = Counter(r.split(":", 1)[1] for a in attendees for r in a.resolutions)
        report = {**payload["report"], "agent_decisions": len(decisions), "agent_outputs_rejected": len(rejected),
                  "agent_outputs_rejected_examples": rejected[:3], "resolutions": dict(actions)}
        self.status = ", ".join(f"{k}: {v}" for k, v in sorted(actions.items())) or "no flags to resolve"
        return Data(data={"attendees": [a.model_dump(mode="json") for a in attendees],
                          "audit": payload["audit"] + [x.model_dump(mode="json", exclude_none=True) for x in audit],
                          "report": report})
