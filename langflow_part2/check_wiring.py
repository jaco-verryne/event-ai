"""Check the hand-wired flow against langflow_part2/WIRING.md, through the Langflow API (local server).

    .venv/bin/python langflow_part2/check_wiring.py

It prints each component, setting and connection with OK or MISSING, so a wiring error shows at once.
"""

import sys

import requests

BASE = "http://127.0.0.1:7860/api/v1"
FLOW_NAME = "Event AI Part 2 Attendee list"

# Component keys: our own names for the 16 components of the guide.
COMPONENTS = {
    "Chat Input": ("ChatInput",), "Load Event": ("LoadEvent",), "Load RSVP Emails": ("LoadRsvpEmails",),
    "Groq": ("LanguageModelComponent",), "OpenRouter": ("LanguageModelComponent",),
    "Extract RSVPs": ("ExtractRsvps",), "Check Records": ("CheckRecords",), "Loop": ("LoopComponent",),
    "Type Convert": ("TypeConverterComponent",), "Agent": ("Agent",), "CRM Lookup": ("CrmLookup",),
    "Invitee Lookup": ("InviteeLookup",), "Company Search": ("CompanySearch",),
    "Agent Decision": ("AgentDecision",), "Apply Decisions": ("ApplyDecisions",), "Write Outputs": ("WriteOutputs",), "Chat Output": ("ChatOutput",),
}
# (step in WIRING.md step 3, from component, output name, to component, input name)
CONNECTIONS = [
    (1, "Chat Input", "message", "Load Event", "event_id"),
    (2, "Load Event", "event", "Load RSVP Emails", "event"),
    (3, "Load Event", "event", "Check Records", "event"),
    (5, "Load RSVP Emails", "emails", "Extract RSVPs", "emails"),
    (6, "Load RSVP Emails", "emails", "Check Records", "emails"),
    (7, "Groq", "model_output", "Extract RSVPs", "primary_model"),
    (8, "OpenRouter", "model_output", "Extract RSVPs", "fallback_model"),
    (9, "OpenRouter", "model_output", "Agent", "model"),
    (10, "Extract RSVPs", "extractions", "Check Records", "extractions"),
    (11, "Check Records", "review_queue", "Loop", "data"),
    (12, "Loop", "item", "Type Convert", "input_data"),
    (13, "Type Convert", "message_output", "Agent", "input_value"),
    (14, "CRM Lookup", "component_as_tool", "Agent", "tools"),
    (15, "Invitee Lookup", "component_as_tool", "Agent", "tools"),
    (16, "Company Search", "component_as_tool", "Agent", "tools"),
    (17, "Agent", "structured_response", "Agent Decision", "decision"),
    (22, "Agent Decision", "decision_out", "Loop", "item"),
    (18, "Loop", "done", "Apply Decisions", "decisions"),
    (19, "Check Records", "checked", "Apply Decisions", "checked"),
    (20, "Apply Decisions", "final", "Write Outputs", "final"),
    (21, "Write Outputs", "summary", "Chat Output", "input_value"),
]
SCHEMA_NAMES = {"attendee_id", "flag", "action", "value", "source", "reason"}


def value(node, field):
    return node["data"]["node"]["template"].get(field, {}).get("value")


def is_zero(number):
    # 0 is falsy, so test for None, not for truth.
    return number is not None and float(number) == 0


def model_name(node):
    chosen = value(node, "model")
    return chosen[0].get("name") if isinstance(chosen, list) and chosen else None


def assign(nodes):
    """Map each guide component to a node of the flow. The two Language Models: the Groq one has the override."""
    found, models = {}, []
    # A tool in Tool Mode first, so that a stray copy of a tool does not hide the real one.
    nodes = sorted(nodes, key=lambda n: not n["data"]["node"].get("tool_mode"))
    for node in nodes:
        # A custom component is saved as "ext:event_ai:LoadEvent@extra".
        kind = node["data"].get("type", "").split(":")[-1].split("@")[0]
        if kind == "LanguageModelComponent":
            models.append(node)
            continue
        for key, kinds in COMPONENTS.items():
            if kind in kinds and key not in found:
                found[key] = node
                break
    for node in models:
        if (value(node, "provider") or "").lower() == "groq" and "Groq" not in found:
            found["Groq"] = node
        elif "OpenRouter" not in found:
            found["OpenRouter"] = node
        elif "Groq" not in found:
            found["Groq"] = node
    return found


def check(flow) -> list[tuple[bool, str]]:
    nodes = [n for n in flow["data"]["nodes"] if n.get("type") == "genericNode"]
    found = assign(nodes)
    ids = {node["id"]: key for key, node in found.items()}
    results = [(flow["name"] == FLOW_NAME, f"flow name is {FLOW_NAME!r} (now {flow['name']!r})")]
    for key in COMPONENTS:
        results.append((key in found, f"component: {key}"))
    kinds = [n["data"].get("type", "").split(":")[-1].split("@")[0] for n in nodes]
    for kind in sorted(set(kinds)):
        allowed = 2 if kind == "LanguageModelComponent" else 1
        if kinds.count(kind) > allowed:
            results.append((False, f"duplicate: {kinds.count(kind)} boxes of {kind}; delete the extra one"))

    edges = set()
    for edge in flow["data"]["edges"]:
        data = edge.get("data", {})
        out = data.get("sourceHandle", {}).get("name")
        target = data.get("targetHandle", {})
        edges.add((ids.get(edge["source"]), out, ids.get(edge["target"]), target.get("fieldName") or target.get("name")))
    for step, src, out, dst, inp in CONNECTIONS:
        results.append(((src, out, dst, inp) in edges, f"connection {step}: {src} · {out} -> {dst} · {inp}"))
    # Removed on 27 Oct: a tool in the Loop must have no input from the start of the flow (WIRING.md).
    results.append(((("Load Event", "event", "Invitee Lookup", "event") not in edges)
                    and "event" not in found.get("Invitee Lookup", {"data": {"node": {"template": {}}}})["data"]["node"]["template"],
                    "connection 4 is gone: Invitee Lookup has no Event input (the new version of the box)"))

    def setting(key, ok, text):
        if key in found:
            results.append((ok(found[key]), f"setting: {key} {text}"))

    setting("Load Event", lambda n: value(n, "source") == "seed", "Source = seed")
    setting("Groq", lambda n: (value(n, "provider") or "").lower() == "groq"
            and value(n, "model_name") == "openai/gpt-oss-120b", "Provider Override = Groq, Model Name Override = openai/gpt-oss-120b")
    setting("Groq", lambda n: is_zero(value(n, "temperature")), "Temperature = 0")
    # The dropdown lists a few paid models only, so the free model comes from the override (or the dropdown).
    setting("OpenRouter", lambda n: "nvidia/nemotron-3.5-super-vl:free" in (value(n, "model_name"), model_name(n))
            and (value(n, "provider") or "OpenRouter").lower() == "openrouter",
            "Model Name Override = nvidia/nemotron-3.5-super-vl:free")
    setting("OpenRouter", lambda n: is_zero(value(n, "temperature")), "Temperature = 0")
    setting("Type Convert", lambda n: value(n, "output_type") == "Message", "Output Type = Message")
    for tool in ("CRM Lookup", "Invitee Lookup", "Company Search"):
        setting(tool, lambda n: bool(n["data"]["node"].get("tool_mode")), "Tool Mode on")
    setting("Agent", lambda n: "You resolve one flag" in (value(n, "system_prompt") or ""), "Agent Instructions pasted")
    setting("Agent", lambda n: int(value(n, "max_iterations") or 0) == 4, "Max Iterations = 4")
    setting("Agent", lambda n: int(value(n, "n_messages") if value(n, "n_messages") is not None else -1) == 0,
            "Number of Chat History Messages = 0")
    setting("Agent", lambda n: not value(n, "add_current_date_tool") and not value(n, "add_calculator_tool"),
            "Current Date and Calculator off")
    setting("Agent", lambda n: {r.get("name") for r in (value(n, "output_schema") or [])} >= SCHEMA_NAMES,
            "Output Schema has attendee_id, flag, action, value, source, reason")
    return results


def main() -> None:
    token = requests.get(f"{BASE}/auto_login", timeout=30).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    flows = requests.get(f"{BASE}/flows/", headers=headers, params={"get_all": "true", "remove_example_flows": "true"},
                         timeout=30).json()
    flows = flows if isinstance(flows, list) else flows.get("items", [])
    wanted = [f for f in flows if f["name"] == FLOW_NAME] or sorted(flows, key=lambda f: f.get("updated_at") or "")[-1:]
    if not wanted:
        sys.exit("No flow found.")
    flow = requests.get(f"{BASE}/flows/{wanted[0]['id']}", headers=headers, timeout=30).json()
    results = check(flow)
    for ok, text in results:
        print(("OK       " if ok else "MISSING  ") + text)
    done = sum(ok for ok, _ in results)
    print(f"\n{done} of {len(results)} checks pass.")


if __name__ == "__main__":
    main()
