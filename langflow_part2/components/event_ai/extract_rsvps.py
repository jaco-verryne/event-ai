"""Langflow component: one LLM call for each email into ExtractedRsvp (step 3), with the D15 provider
order: the primary model first, the fallback model when the primary one fails."""

from collections import Counter

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from lfx.custom import Component
from lfx.io import HandleInput, Output
from lfx.schema import DataFrame

from eventai.agent.extract import extract_rsvp
from eventai.agent.flow_io import records
from eventai.agent.schema import Email

_ROLES = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


class ExtractRsvps(Component):
    display_name = "Extract RSVPs"
    description = "Reads each email with the LLM into a fixed schema. Null when the email does not give a value."
    icon = "scan-text"
    name = "ExtractRsvps"

    inputs = [
        HandleInput(name="emails", display_name="Emails", input_types=["DataFrame", "Table"], required=True),
        HandleInput(name="primary_model", display_name="Primary model", input_types=["LanguageModel"], required=True,
                    info="Groq openai/gpt-oss-120b, temperature 0 (D15)."),
        HandleInput(name="fallback_model", display_name="Fallback model", input_types=["LanguageModel"],
                    required=False, info="OpenRouter nvidia/nemotron-3.5-super-vl:free, for a rate limit or an error."),
    ]
    outputs = [Output(name="extractions", display_name="Extractions", method="extract")]

    def _complete(self, model):
        bound = model.bind(response_format={"type": "json_object"})
        callbacks = self.get_langchain_callbacks()  # the calls show in the trace of the run

        def complete(messages):
            reply = bound.invoke([_ROLES[m["role"]](content=m["content"]) for m in messages],
                                 config={"callbacks": callbacks})
            return reply.content if isinstance(reply.content, str) else str(reply.content)

        return complete

    def extract(self) -> DataFrame:
        emails = [Email.model_validate(row) for row in records(self.emails)]
        models = [("primary", self.primary_model), ("fallback", self.fallback_model)]
        rows, used = [], Counter()
        for email in emails:
            row = {"email_key": email.key, "model": None, "error": None}
            for label, model in models:
                if model is None:
                    continue
                try:
                    extracted = extract_rsvp(email, self._complete(model))
                except Exception as err:  # noqa: BLE001 - a rate limit, a provider error or invalid output
                    row["error"] = f"{label}: {type(err).__name__}: {err}"[:300]
                    continue
                row.update(extracted.model_dump(), model=label, error=None)
                break
            used[row["model"] or "failed"] += 1
            rows.append(row)
        self.status = ", ".join(f"{k}: {v}" for k, v in sorted(used.items()))
        return DataFrame(rows)
