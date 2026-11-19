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

Vendor-specific rules and examples come from the vendor profiles (ibn/vendors/):
the AI only gets the notes of the vendors that are in the network.

The plan is only a PROPOSAL. The validation layer checks it next.
"""
import json

from ..vendors import get_vendor

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
                },
                "required": ["device", "type", "commands", "rollback"],
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

Rules:
- Only use devices from the list. Use each device's exact "name".
- Write commands in the CLI syntax of the device's "vendor" (see the vendor notes below).
- Use the real interface names and IP addresses from "interfaces" below.
  To reach a device, ping one of ITS interface IPs (not the 192.168.x management IP,
  unless the user asks for management).
- Use ONLY interface names that appear in that device's "interfaces"
  (e.g. if it has "Ethernet0/0", never write "GigabitEthernet0/0").
- If the request is unclear or impossible, return no steps and explain why in "summary".

Vendor notes and examples:
{vendor_notes}

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
    plan["intent"] = text
    return plan


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
