"""Langflow component: the planner brief (D17). After the list is final, it asks Part 1, the RAG pipeline,
what the company's policies require for this event, and adds the cited answers and dated actions.

Part 1 runs in its own venv (.venv): Langflow pins older duckdb, pydantic and langfuse, so this component
starts `python -m eventai.agent.brief` there. A failure records an error, and the run goes on."""

import json
import os
import subprocess

from lfx.custom import Component
from lfx.io import BoolInput, HandleInput, Output
from lfx.schema import Data

from eventai.config import ROOT

TIMEOUT_SECONDS = 900  # 4 questions, each may wait for Groq's next minute


class PlannerBrief(Component):
    display_name = "Planner Brief"
    description = ("Asks Part 1, the knowledge-base assistant, what the policies require for this event: "
                   "deadlines, dietary rules, the venue and access, data retention. Cited answers and dated actions.")
    icon = "clipboard-list"
    name = "PlannerBrief"

    inputs = [
        HandleInput(name="final", display_name="Final records", input_types=["Data", "JSON"], required=True),
        BoolInput(name="dry_run", display_name="Dry run", value=False, advanced=True,
                  info="The questions only, with no LLM call (for the smoke test)."),
    ]
    outputs = [Output(name="final_with_brief", display_name="Final records", method="final_with_brief")]

    def final_with_brief(self) -> Data:
        payload = dict(self.final.data)
        event = payload["event"]
        request = {"event": event, "attendees": payload["attendees"],
                   "session_id": f"part2-{event['event_id']}-{getattr(self.graph, 'run_id', '') or ''}".rstrip("-")}
        command = [str(ROOT / ".venv" / "bin" / "python"), "-m", "eventai.agent.brief"]
        if self.dry_run:
            command.append("--dry-run")
        try:
            done = subprocess.run(command, input=json.dumps(request), capture_output=True, text=True, check=True,
                                  timeout=TIMEOUT_SECONDS, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
            brief = json.loads(done.stdout)
        except (subprocess.SubprocessError, OSError, ValueError) as err:
            brief = {"event_id": event["event_id"], "error": f"{type(err).__name__}: {err}"[:300],
                     "stderr": (getattr(err, "stderr", "") or "")[-500:]}
        payload["brief"] = brief
        if "error" in brief:
            self.status = f"brief failed: {brief['error']}"
        elif brief.get("dry_run"):
            self.status = f"dry run: {len(brief['questions'])} questions"
        else:
            self.status = f"{len(brief['answers'])} answers, {len(brief['deadlines'])} deadlines"
        return Data(data=payload)
