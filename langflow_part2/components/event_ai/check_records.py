"""Langflow component: the code checks (steps 4-7) and the queue of flagged records for the agent."""

from lfx.custom import Component
from lfx.io import HandleInput, Output
from lfx.schema import Data, DataFrame

from eventai.agent import checks
from eventai.agent.flow_io import records
from eventai.agent.review import review_items
from eventai.agent.schema import Email, Event, ExtractedRsvp
from eventai.agent.tools import seed_files
from eventai.agent.tools.companies_house import CompaniesHouse
from eventai.config import load_settings


class CheckRecords(Component):
    display_name = "Check Records"
    description = ("Plain code: grounding, normalization, deduplication, and verification against the CRM, "
                   "the invitee list, Companies House and the venue capacity (Part 1 venues.csv).")
    icon = "shield-check"
    name = "CheckRecords"

    inputs = [
        HandleInput(name="event", display_name="Event", input_types=["Data", "JSON"], required=True),
        HandleInput(name="emails", display_name="Emails", input_types=["DataFrame", "Table"], required=True),
        HandleInput(name="extractions", display_name="Extractions", input_types=["DataFrame", "Table"], required=True),
    ]
    outputs = [
        Output(name="checked", display_name="Checked records", method="checked", group_outputs=True),
        Output(name="review_queue", display_name="Review queue", method="review_queue", group_outputs=True),
    ]

    def _run(self):
        # Both outputs need one result; compute it once for the run.
        if getattr(self, "_result", None) is None:
            event = Event.model_validate(self.event.data)
            emails = [Email.model_validate(row) for row in records(self.emails)]
            by_key = {e.key: e for e in emails}
            pairs, failed = [], []
            for row in records(self.extractions):
                if row.get("error") or row.get("email_key") not in by_key:
                    failed.append(row.get("email_key"))
                    continue
                pairs.append((by_key[row["email_key"]], ExtractedRsvp.model_validate(row)))
            house = CompaniesHouse(load_settings().companies_house_api_key)
            attendees, audit, report = checks.check_all(
                pairs, event=event, crm=seed_files.load_crm(), companies=house.check,
                seated_capacity=seed_files.venue_capacity(event.venue_id))
            report.update(extraction_failed=failed, companies_house_requests=house.requests_sent)
            self._result = (event, emails, attendees, audit, report)
            self.status = f"{len(attendees)} records, {len(report['for_review'])} for review"
        return self._result

    def checked(self) -> Data:
        event, emails, attendees, audit, report = self._run()
        return Data(data={
            "event": event.model_dump(mode="json"),
            "emails": [e.model_dump(mode="json") for e in emails],
            "attendees": [a.model_dump(mode="json") for a in attendees],
            "audit": [x.model_dump(mode="json", exclude_none=True) for x in audit],
            "report": report,
        })

    def review_queue(self) -> DataFrame:
        _, emails, attendees, _, _ = self._run()
        return DataFrame(review_items(attendees, emails))
