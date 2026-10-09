"""MikroTik RouterOS."""
from .base import VendorProfile

PROFILE = VendorProfile(
    name="mikrotik_routeros",
    description="MikroTik RouterOS",

    netmiko_type="mikrotik_routeros",
    show_config="/export",
    error_markers=["failure:", "bad command name", "syntax error", "expected end of command"],

    check_commands=r"^(/ping|/tool traceroute|/\S.* print)\b",
    blocked=[
        (r"^/system (reboot|reset-configuration|shutdown)", "restarts or wipes the router"),
        (r"^/user remove", "can lock us out of the router"),
        (r"^/file remove", "deletes files"),
    ],
    warn=[
        (r"disabled=yes", "turns something off"),
        (r"^/ip firewall", "a firewall rule can block traffic, including ours"),
    ],

    ai_hints="""\
- Commands are full paths, e.g. "/ip address add address=10.0.5.1/24 interface=ether2".
- Check commands: /ping <ip> count=4, /ip address print, /ip route print.

Example:
Request: "add 10.0.5.1/24 on ether2 of MT1"
{"summary": "Add 10.0.5.1/24 on ether2 of MT1",
 "changes": [{"device": "MT1", "type": "config",
              "commands": ["/ip address add address=10.0.5.1/24 interface=ether2"],
              "rollback": ["/ip address remove [find address=\\"10.0.5.1/24\\"]"]}]}""",
)
