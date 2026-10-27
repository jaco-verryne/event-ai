"""A smoke test of the Event AI components, with no LLM call: a fake model gives the canned extraction for
each seed email (tests/fixtures). The agent step is left out; Apply Decisions then sends each flag to
human review, and the planner brief runs dry (questions only). Run it with langflow_part2/smoke.sh."""

import json
import os
from pathlib import Path

import yaml
from event_ai.apply_decisions import ApplyDecisions
from event_ai.check_records import CheckRecords
from event_ai.extract_rsvps import ExtractRsvps
from event_ai.load_event import LoadEvent
from event_ai.load_rsvp_emails import LoadRsvpEmails
from event_ai.planner_brief import PlannerBrief
from event_ai.write_outputs import WriteOutputs
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from lfx.components.input_output.chat import ChatInput
from lfx.components.input_output.chat_output import ChatOutput
from lfx.graph import Graph

ROOT = Path(__file__).resolve().parent.parent


def get_graph() -> Graph:
    canned = yaml.safe_load((ROOT / "tests" / "fixtures" / "part2_extractions.yaml").read_text())
    fake = FakeListChatModel(responses=[json.dumps(canned[f"e{i:02d}"]) for i in range(1, 14)])
    start = ChatInput()
    event = LoadEvent().set(event_id=start.message_response, source="seed")
    emails = LoadRsvpEmails().set(event=event.load_event)
    extract = ExtractRsvps().set(emails=emails.load_emails, primary_model=fake)
    check = CheckRecords().set(event=event.load_event, emails=emails.load_emails, extractions=extract.extract)
    apply = ApplyDecisions().set(checked=check.checked)
    brief = PlannerBrief().set(final=apply.apply, dry_run=True)
    write = WriteOutputs().set(final=brief.final_with_brief, out_dir=os.environ["SMOKE_OUT"])
    return Graph(start, ChatOutput().set(input_value=write.write))
