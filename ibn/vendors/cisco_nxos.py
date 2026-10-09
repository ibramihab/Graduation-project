"""Cisco NX-OS (Nexus switches). Same safety rules as IOS, different examples."""
from dataclasses import replace

from .cisco_ios import PROFILE as IOS

PROFILE = replace(
    IOS,
    name="cisco_nxos",
    description="Cisco NX-OS",
    netmiko_type="cisco_nxos",
    wrapper_lines=IOS.wrapper_lines | {"copy running-config startup-config"},
    ai_hints="""\
- Like Cisco IOS: config steps run in configuration mode, do NOT add "configure terminal" or "end".
- Check commands: show ..., ping, traceroute.
- Interfaces look like Ethernet1/1. Features may need enabling first (e.g. "feature interface-vlan").

Example:
Request: "create vlan 40 named Lab on NX1"
{"summary": "Create VLAN 40 named Lab on NX1",
 "changes": [{"device": "NX1", "type": "config",
              "commands": ["vlan 40", "name Lab"], "rollback": ["no vlan 40"]}]}""",
)
