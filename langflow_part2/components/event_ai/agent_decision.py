"""Langflow component: the end of the loop body. It passes the Agent's Structured Response to the Loop.

Langflow's Loop collects the FIRST output of the last component in its body. For the Agent that is its
text Response, not the Structured Response, even when only the Structured Response is connected. With
this one-output component as the last one, the Loop collects the decision, and the Agent runs once."""

from lfx.custom import Component
from lfx.io import HandleInput, Output
from lfx.schema import Data


class AgentDecision(Component):
    display_name = "Agent Decision"
    description = "Closes the loop: connect the Agent's Structured Response here, and this output to the Loop's Item."
    icon = "gavel"
    name = "AgentDecision"

    inputs = [HandleInput(name="decision", display_name="Structured Response", input_types=["Data", "JSON"],
                          required=True)]
    outputs = [Output(name="decision_out", display_name="Decision", method="decision_out")]

    def decision_out(self) -> Data:
        payload = self.decision.data if hasattr(self.decision, "data") else {}
        self.status = f"{payload.get('attendee_id', '?')} {payload.get('flag', '?')}: {payload.get('action', payload.get('error', '?'))}"
        return self.decision
