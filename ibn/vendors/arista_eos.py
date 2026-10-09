"""Arista EOS switches. Very close to Cisco IOS syntax."""
from dataclasses import replace

from .cisco_ios import PROFILE as IOS

PROFILE = replace(
    IOS,
    name="arista_eos",
    description="Arista EOS",
    netmiko_type="arista_eos",
    neighbors="",  # Arista uses LLDP, not CDP (not supported yet)
    ai_hints="""\
- Like Cisco IOS: config steps run in configuration mode, do NOT add "configure terminal" or "end".
- Check commands: show ..., ping, traceroute.
- Interfaces look like Ethernet1.

Example:
Request: "create vlan 50 named Voice on AR1"
{"summary": "Create VLAN 50 named Voice on AR1",
 "changes": [{"device": "AR1", "type": "config",
              "commands": ["vlan 50", "name Voice"], "rollback": ["no vlan 50"]}]}""",
)
