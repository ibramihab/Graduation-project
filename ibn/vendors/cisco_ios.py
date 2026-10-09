"""Cisco IOS / IOS-XE / IOL (routers and switches)."""
from .base import VendorProfile

PROFILE = VendorProfile(
    name="cisco_ios",
    description="Cisco IOS",

    netmiko_type="cisco_ios",
    show_config="show running-config",
    show_interfaces="show ip interface brief",
    neighbors="cdp",
    error_markers=["% Invalid", "% Incomplete", "% Ambiguous", "% Unknown"],

    check_commands=r"^(show|ping|traceroute)\b",
    blocked=[
        (r"^reload", "restarts the device"),
        (r"^(erase|format|delete|write erase)", "deletes files or the whole config"),
        (r"^no username", "can lock us out of the device"),
        (r"^no (ip )?ssh|^line vty .*\btransport input none", "can cut our SSH access"),
        (r"^crypto key zeroize", "deletes the SSH keys"),
        (r"^no aaa new-model", "changes how logins work"),
        (r"^enable secret|^enable password", "changes the enable password"),
    ],
    warn=[
        (r"^shutdown$", "turns an interface off"),
        (r"^no ip address", "removes an IP address (could be the management IP)"),
        (r"^no (vlan|interface|router)", "removes something that may be in use"),
        (r"access-list|access-group", "a firewall rule can block traffic, including ours"),
    ],

    wrapper_lines={"configure terminal", "conf t", "end", "write memory", "wr"},
    ai_hints="""\
- Config steps run in configuration mode: do NOT add "configure terminal", "end" or "write memory".
- Check commands: show ..., ping, traceroute.
- VLANs are created on switches (names starting with SW).
- Interface settings: first a line "interface <name>", then its settings on the next lines.
  Example: ["interface Ethernet0/0", "ip access-group BLOCK in"].
  Never write a setting and the interface on one line.
- To block traffic, use an extended access list with a "deny" for the traffic to block
  and "permit ip any any" at the end. Apply it INBOUND ("in") on the interfaces of the
  device that should not receive the traffic (outbound ACLs do not filter traffic the
  router creates itself). The rollback removes it from the interfaces first, then
  deletes the list.

Examples:
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

Request: "stop the network 10.0.1.0/24 from reaching R2"   (R2 receives it on Ethernet0/0)
{"summary": "On R2, deny traffic from 10.0.1.0/24 coming in on Ethernet0/0",
 "changes": [{"device": "R2", "type": "config",
              "commands": ["ip access-list extended BLOCK-10-0-1",
                           "deny ip 10.0.1.0 0.0.0.255 any",
                           "permit ip any any",
                           "interface Ethernet0/0",
                           "ip access-group BLOCK-10-0-1 in"],
              "rollback": ["interface Ethernet0/0",
                           "no ip access-group BLOCK-10-0-1 in",
                           "exit",
                           "no ip access-list extended BLOCK-10-0-1"]}]}""",
)
