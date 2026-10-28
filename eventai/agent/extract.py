"""RSVP extraction: one LLM call for each email, into ExtractedRsvp (CLAUDE.md 10.1, step 3).

Framework-independent: `complete` is any function that sends chat messages to a model and returns the
reply text. The Langflow component passes Groq first and OpenRouter as the fallback (D15).
"""

import json
from collections.abc import Callable

from eventai.agent.schema import Email, ExtractedRsvp

Complete = Callable[[list[dict[str, str]]], str]

PROMPT = """You read one email that names a company event. Most of them are RSVPs. Return one JSON object with the
keys is_rsvp (true or false), full_name, email, phone, company, job_title, dietary_needs (each a string or null)
and attending (true, false or null).

Rules:
- is_rsvp is false only when the email is not from a guest about this event: an automatic reply (for example
  out of office), a message from a supplier or a venue, a newsletter or an advert. A guest's reply, change,
  question, or note about a dietary need or a substitute is an RSVP (true).
- Copy each value exactly as the email writes it. Do not correct the spelling, the case or the format.
- Use null when the email does not give a value. Do not infer a value, and do not invent one.
- full_name and email belong to the person who writes the email.
- attending is true for a clear yes, false for a clear no, and null when the reply is not clear.
- dietary_needs holds only food needs or allergies, in the email's words but without the rest of the sentence
  (for example "no nuts", not "no nuts for me, please").
Reply with the JSON object only."""


class ExtractionFailed(Exception):
    """The model gave no valid JSON after one retry."""


def messages_for(email: Email) -> list[dict[str, str]]:
    schema = json.dumps(ExtractedRsvp.model_json_schema())
    return [
        {"role": "system", "content": f"{PROMPT}\n\nJSON schema:\n{schema}"},
        {"role": "user", "content": email.text},
    ]


def parse(text: str) -> ExtractedRsvp:
    text = text.strip()
    if text.startswith("```"):  # some models wrap JSON in a code fence
        text = text.strip("`").removeprefix("json").strip()
    return ExtractedRsvp.model_validate_json(text)


def extract_rsvp(email: Email, complete: Complete) -> ExtractedRsvp:
    """One call; one retry with the validation error when the output is not valid."""
    messages = messages_for(email)
    reply = complete(messages)
    try:
        return parse(reply)
    except ValueError as err:
        messages = [*messages, {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Your JSON is not valid:\n{err}\nReply again with one valid JSON object only."}]
    reply = complete(messages)
    try:
        return parse(reply)
    except ValueError as err:
        raise ExtractionFailed(f"{email.key}: {err}") from err
