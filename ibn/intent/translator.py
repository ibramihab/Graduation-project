"""Intent layer: turns plain English into a config PLAN.

    "create vlan 10 named Sales on SW1"
            |
            v
    {"summary": "...",
     "changes": [{"device": "SW1",
                  "commands": ["vlan 10", "name Sales"],
                  "rollback": ["no vlan 10"]}]}

The plan is only a PROPOSAL. The validation layer checks it next.
"""
import json

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
                    "commands": {"type": "array", "items": {"type": "string"}},
                    "rollback": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["device", "commands", "rollback"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are a network engineer inside an intent-based networking system.
Turn the user's request into configuration changes for the devices listed below.

Rules:
- Only use devices from the list. Use each device's exact "name".
- Write commands in the CLI syntax of the device's "vendor" (e.g. cisco_ios = Cisco IOS).
- Give only configuration-mode lines. Do NOT add "configure terminal", "end" or "write memory".
- For every change also give "rollback": the commands that undo it.
- For vendor "web_gui" (home routers with only a web page), write short English steps
  instead of CLI, for example "set wifi name to Home5G".
- If the request is unclear or impossible, return no changes and explain why in "summary".

Devices:
{devices}
"""

# Lines the control layer adds by itself, so we remove them if the LLM adds them anyway.
WRAPPER_LINES = {"configure terminal", "conf t", "end", "write memory", "wr"}


def translate(text: str, devices: list[dict], llm) -> dict:
    # Only send the LLM what it needs (never passwords).
    visible = [{k: d.get(k) for k in ("name", "ip", "vendor", "state")} for d in devices]
    system = SYSTEM_PROMPT.format(devices=json.dumps(visible, indent=2))
    plan = llm.ask_json(system, text, PLAN_SCHEMA)

    for change in plan["changes"]:
        change["commands"] = _clean(change["commands"])
        change["rollback"] = _clean(change["rollback"])
    plan["intent"] = text
    return plan


def _clean(lines: list[str]) -> list[str]:
    return [l.strip() for l in lines if l.strip() and l.strip().lower() not in WRAPPER_LINES]
