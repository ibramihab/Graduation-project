"""Intent layer: turns plain English into a PLAN.

    "create vlan 10 named Sales on SW1"
            |
            v
    {"summary": "...",
     "changes": [{"device": "SW1", "type": "config",
                  "commands": ["vlan 10", "name Sales"],
                  "rollback": ["no vlan 10"]}]}

Each step has a type:
    "config" = changes the device (configure terminal mode), needs a rollback
    "check"  = read-only commands like ping / show (exec mode), no rollback

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
- "config": changes the configuration. Commands run in configuration mode.
  Do NOT add "configure terminal", "end" or "write memory".
  Give "rollback": the commands that undo the change.
- "check": read-only commands that run in normal (exec) mode, like
  "ping", "show ...", "traceroute". Use this when the user wants to test, check,
  verify, see or show something. "rollback" must be [] (empty).
Never put ping/show/traceroute in a "config" step.

Rules:
- Only use devices from the list. Use each device's exact "name".
- Write commands in the CLI syntax of the device's "vendor" (cisco_ios = Cisco IOS).
- Use the real interface names and IP addresses from "interfaces" below.
  To reach a device, ping one of ITS interface IPs (not the 192.168.x management IP,
  unless the user asks for management).
- On Cisco, VLANs are created on switches (names starting with SW).
- For vendor "web_gui" (home routers with only a web page), write short English steps
  instead of CLI, for example "set wifi name to Home5G".
- If the request is unclear or impossible, return no steps and explain why in "summary".

Examples (Cisco IOS):
Request: "create vlan 20 named Finance on SW3"
{"summary": "Create VLAN 20 named Finance on SW3",
 "changes": [{"device": "SW3", "type": "config",
              "commands": ["vlan 20", "name Finance"], "rollback": ["no vlan 20"]}]}

Request: "ping from R1 to R3"   (R3 has interface Ethernet0/1 10.2.3.3)
{"summary": "Ping R3's interface 10.2.3.3 from R1",
 "changes": [{"device": "R1", "type": "check",
              "commands": ["ping 10.2.3.3"], "rollback": []}]}

Request: "add loopback 5 with ip 5.5.5.5/32 on R2 and show the interfaces"
{"summary": "Create Loopback5 on R2 then show interfaces",
 "changes": [{"device": "R2", "type": "config",
              "commands": ["interface Loopback5", "ip address 5.5.5.5 255.255.255.255"],
              "rollback": ["no interface Loopback5"]},
             {"device": "R2", "type": "check",
              "commands": ["show ip interface brief"], "rollback": []}]}

Devices:
{devices}
"""

# Lines the control layer adds by itself, so we remove them if the LLM adds them anyway.
WRAPPER_LINES = {"configure terminal", "conf t", "end", "write memory", "wr"}


def translate(text: str, devices: list[dict], llm) -> dict:
    # Only send the LLM what it needs (never passwords).
    fields = ("name", "ip", "vendor", "state", "interfaces")
    visible = [{k: d[k] for k in fields if d.get(k)} for d in devices]
    # .replace (not .format) because the examples above contain { } braces
    system = SYSTEM_PROMPT.replace("{devices}", json.dumps(visible, indent=2))
    plan = llm.ask_json(system, text, PLAN_SCHEMA)

    for change in plan["changes"]:
        change.setdefault("type", "config")
        change["commands"] = _clean(change["commands"])
        change["rollback"] = _clean(change.get("rollback", []))
    plan["intent"] = text
    return plan


def _clean(lines: list[str]) -> list[str]:
    return [l.strip() for l in lines if l.strip() and l.strip().lower() not in WRAPPER_LINES]
