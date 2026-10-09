"""Fortinet FortiGate firewalls (FortiOS)."""
import re

from .base import VendorProfile


def fortigate_interfaces(output: str) -> list[str]:
    """Read "show system interface" (FortiOS config format):
        config system interface
            edit "port1"
                set ip 192.168.1.99 255.255.255.0
            next
            edit "port2"
            next
        end
    -> ["port1 192.168.1.99", "port2 unassigned"]
    Only top-level "edit" lines count (not nested ones like secondary IPs)."""
    interfaces, name, depth = {}, None, 0
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("config "):
            depth += 1
        elif line == "end":
            depth -= 1
        elif depth == 1 and (match := re.match(r'edit "?([^"]+)"?$', line)):
            name = match[1]
            interfaces[name] = "unassigned"
        elif depth == 1 and name and (match := re.match(r"set ip (\S+)", line)):
            interfaces[name] = match[1]
        elif depth == 1 and line == "next":
            name = None
    return [f"{n} {ip}" for n, ip in interfaces.items()]


PROFILE = VendorProfile(
    name="fortigate",
    description="Fortinet FortiGate (FortiOS)",

    netmiko_type="fortinet",
    show_config="show",
    show_interfaces="show system interface",
    parse_interfaces=fortigate_interfaces,
    error_markers=["Command fail", "Unknown action", "parse error", "value parse error",
                   "entry not found", "node_check_object fail"],

    check_commands=r"^(get|show|execute (ping|ping-options|traceroute))\b",
    blocked=[
        (r"^execute (reboot|shutdown|factoryreset|factoryreset2|formatlogdisk|erase-disk|restore)",
         "restarts, wipes or replaces the firewall config"),
        (r"^config system admin", "changes admin accounts (can lock us out)"),
        (r"^purge\b", "deletes every entry of a table"),
    ],
    warn=[
        (r"^set status down", "turns an interface off"),
        (r"allowaccess", "changes how the firewall can be managed (could lock us out)"),
        (r"^config firewall policy", "a firewall policy can block traffic, including ours"),
        (r"^delete\b", "removes something that may be in use"),
    ],

    # FortiOS has no separate config mode, and "next"/"end" are PART of the config,
    # so nothing is removed from the AI's answer.
    wrapper_lines=set(),
    ai_hints="""\
- FortiOS config is in blocks: "config <section>", then "edit <name or id>", "set ..." lines,
  "next" after each entry, and "end" to close the block. ALWAYS close every block with "end".
- Check commands: get ..., show ..., execute ping <ip>, execute traceroute <ip>.
- Interfaces are named like port1, port2 (use the names from "interfaces").
- Firewall policies: use an explicit policy ID of 1000 or more (never "edit 0"), so the
  rollback can delete it: "config firewall policy", "delete <id>", "end".
- A policy needs: name, srcintf, dstintf, srcaddr, dstaddr, action, schedule "always", service.

Examples:
Request: "set IP 10.0.5.1/24 on port2 of FW1 and allow ping on it"
{"summary": "Configure 10.0.5.1/24 on port2 of FW1 with ping allowed",
 "changes": [{"device": "FW1", "type": "config",
              "commands": ["config system interface", "edit \\"port2\\"",
                           "set ip 10.0.5.1 255.255.255.0", "set allowaccess ping", "next", "end"],
              "rollback": ["config system interface", "edit \\"port2\\"",
                           "unset ip", "unset allowaccess", "next", "end"]}]}

Request: "block traffic from port2 to port1 on FW1"
{"summary": "Deny all traffic from port2 to port1 on FW1 with policy 1001",
 "changes": [{"device": "FW1", "type": "config",
              "commands": ["config firewall policy", "edit 1001", "set name \\"block-p2-p1\\"",
                           "set srcintf \\"port2\\"", "set dstintf \\"port1\\"",
                           "set srcaddr \\"all\\"", "set dstaddr \\"all\\"", "set action deny",
                           "set schedule \\"always\\"", "set service \\"ALL\\"", "next", "end"],
              "rollback": ["config firewall policy", "delete 1001", "end"]}]}

Request: "show the routing table of FW1"
{"summary": "Show FW1's routing table",
 "changes": [{"device": "FW1", "type": "check",
              "commands": ["get router info routing-table all"], "rollback": []}]}""",
)
