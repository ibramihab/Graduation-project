"""Intent layer: turns plain English into a PLAN.

    "create vlan 10 named Sales on SW1"
            |
            v
    {"summary": "...",
     "changes": [{"device": "SW1", "type": "config",
                  "commands": ["vlan 10", "name Sales"],
                  "rollback": ["no vlan 10"]}]}

Each step has a type:
    "config" = changes the device (configuration mode), needs a rollback
    "check"  = read-only commands like ping / show (exec mode), no rollback
A "config" step can also have "verify": read-only commands (ping, show) that the
control layer runs AFTER applying, to prove the intent really happened (post-validation).

If the request is missing something (which device? which network?), the AI must not
guess: it returns no steps and a summary starting with "QUESTION:". translate() then
puts that question in plan["question"] so the web page can ask the user.

Vendor-specific rules and examples come from the vendor profiles (ibn/vendors/):
the AI only gets the notes of the vendors that are in the network.

The plan is only a PROPOSAL. The validation layer checks it next.
"""
import json

from ..vendors import get_vendor
from .rag import retrieve

# The exact shape the LLM must answer with.
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "type": {"type": "string", "enum": ["config", "check"]},
                    "commands": {"type": "array", "items": {"type": "string"}},
                    "rollback": {"type": "array", "items": {"type": "string"}},
                    "verify": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["device", "type", "commands", "rollback", "verify"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are a network engineer inside an intent-based networking system.
Turn the user's request into steps for the devices listed below.

Each step has a "type":
- "config": changes the configuration. Give "rollback": the commands that undo the change.
- "check": read-only commands (each vendor's notes say which ones: show, display, ping...).
  Use this when the user wants to test, check, verify, see or show something.
  "rollback" must be [] (empty). Never put check commands in a "config" step.

"verify" (post-validation): for a "config" step, 1 or 2 read-only check commands that
prove the change WORKED, run after everything is applied. If a verify command fails,
everything is rolled back, so only ping when the user's goal IS reachability to a device
in the list ("R1 should reach R3": ping one of R3's interface IPs). Otherwise use a show
command that displays the new setting ("show vlan brief", "show ip route static").
Use [] for "check" steps.

Rules:
- Only use devices from the list. Use each device's exact "name".
- Write commands in the CLI syntax of the device's "vendor" (see the vendor notes below),
  each command in FULL (never abbreviations like "sh", "int", "conf t"): the syntax
  check refuses commands it doesn't know.
- Use the real interface names and IP addresses from "interfaces" below.
  To reach a device, ping one of ITS interface IPs (not the 192.168.x management IP,
  unless the user asks for management).
- Use ONLY interface names that appear in that device's "interfaces"
  (e.g. if it has "Ethernet0/0", never write "GigabitEthernet0/0").
- The user may describe a device instead of naming it ("the router connected to SW1",
  "the switch behind R2"). Find it using the "Links" list, then use its exact name.
- The request may ask for several things ("create vlan 10 and ping R2"): make one step
  for each, in the order asked.
- If the request is impossible (unknown device, not possible on these devices),
  return no steps and explain why in "summary".
- If information is MISSING (which device, which network, which next hop, which VLAN
  number...), do NOT guess. Return no steps, and make "summary" ONE short question that
  starts with "QUESTION:" and asks exactly what is missing. Example:
  Request: "configure static routing"
  {"summary": "QUESTION: On which router, to which network, and via which next hop?",
   "changes": []}

Vendor notes and examples:
{vendor_notes}
{rag}
Devices:
{devices}

Links (cables between devices):
{links}
"""


def translate(text: str, devices: list[dict], llm, links: list[dict] = ()) -> dict:
    # Only send the LLM what it needs (never passwords).
    fields = ("name", "ip", "vendor", "state", "interfaces")
    visible = [{k: d[k] for k in fields if d.get(k)} for d in devices]
    # .replace (not .format) because the examples contain { } braces
    system = SYSTEM_PROMPT.replace("{vendor_notes}", _vendor_notes(devices))
    system = system.replace("{rag}", _rag(text, devices))
    system = system.replace("{devices}", json.dumps(visible, indent=2))
    system = system.replace("{links}", "\n".join(f"{l['a']} - {l['b']}" for l in links) or "(unknown)")
    plan = llm.ask_json(system, text, PLAN_SCHEMA)

    vendor_of = {d["name"]: d.get("vendor") for d in devices}
    for change in plan["changes"]:
        change.setdefault("type", "config")
        profile = get_vendor(vendor_of.get(change.get("device")))
        wrapper = profile.wrapper_lines if profile else set()
        change["commands"] = _clean(change["commands"], wrapper)
        change["rollback"] = _clean(change.get("rollback", []), wrapper)
        # Only config steps are verified (a check step already IS a check).
        verify = change.get("verify", []) if change["type"] == "config" else []
        change["verify"] = _clean(verify, wrapper)
    plan["intent"] = text
    question = _question(plan)
    if question:
        plan["question"] = question
    return plan


def _rag(text: str, devices: list[dict]) -> str:
    """RAG: the closest solved examples for these vendors (ibn/intent/rag/), or nothing."""
    found = retrieve(text, [d.get("vendor") for d in devices])
    if not found:
        return ""
    return ("\nThe examples below come from another network: copy the method, but take the device\n"
            "names, interfaces and IPs from the lists further down.\n\n" + found + "\n")


def _question(plan: dict) -> str:
    """The AI's question when the request was missing information, else ""."""
    summary = plan.get("summary", "").strip()
    if plan["changes"] or not summary.upper().startswith("QUESTION:"):
        return ""
    return summary[len("QUESTION:"):].strip()


def _vendor_notes(devices: list[dict]) -> str:
    """Notes + examples only for the vendors that are in the network (shorter prompt)."""
    notes, seen = [], set()
    for vendor in dict.fromkeys(d.get("vendor") for d in devices):
        profile = get_vendor(vendor)
        if profile and profile.ai_hints not in seen:
            seen.add(profile.ai_hints)
            notes.append(f"## {profile.description} (vendor \"{profile.name}\")\n{profile.ai_hints}")
    return "\n\n".join(notes) or "(no known vendors)"


def _clean(lines: list[str], wrapper: set[str]) -> list[str]:
    """Remove empty lines and lines the driver adds by itself (e.g. "configure terminal")."""
    return [l.strip() for l in lines if l.strip() and l.strip().lower() not in wrapper]
