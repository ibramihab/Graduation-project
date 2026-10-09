"""Huawei VRP (routers and switches: AR, NE, S series...)."""
from .base import VendorProfile

PROFILE = VendorProfile(
    name="huawei",
    description="Huawei VRP",

    netmiko_type="huawei",
    show_config="display current-configuration",
    show_interfaces="display ip interface brief",
    error_markers=["Error:", "Unrecognized command", "Wrong parameter", "Incomplete command"],

    check_commands=r"^(display|ping|tracert)\b",
    blocked=[
        (r"^reboot", "restarts the device"),
        (r"^reset saved-configuration", "erases the saved config"),
        (r"^(format|delete)\b", "deletes files"),
        (r"^undo local-user", "can lock us out of the device"),
        (r"^local-user \S+ password", "changes a login password"),
        (r"^undo (stelnet|ssh|telnet) server", "can cut our SSH/Telnet access"),
    ],
    warn=[
        (r"^shutdown$", "turns an interface off"),
        (r"^undo ip address", "removes an IP address (could be the management IP)"),
        (r"^undo (vlan|interface)", "removes something that may be in use"),
        (r"traffic-filter|^acl\b|^rule\b", "a firewall rule can block traffic, including ours"),
    ],

    # Netmiko enters "system-view" and leaves with "return" by itself.
    wrapper_lines={"system-view", "sys", "return", "save"},
    ai_hints="""\
- Config steps run in system view: do NOT add "system-view", "return" or "save".
- Check commands: display ..., ping, tracert.
- Huawei uses "undo" instead of "no" (e.g. "undo vlan 10", "undo shutdown").
- Interface names look like GigabitEthernet0/0/1 (three numbers). Interface settings:
  first "interface <name>", then the settings, then "quit" to leave the interface view.
- VLANs: "vlan 10" (one) or "vlan batch 10 20" (many). Access port:
  "port link-type access" + "port default vlan 10".
- To block traffic: an advanced ACL ("acl number 3000", "rule 5 deny ip source <net> <wildcard>",
  "rule 100 permit ip") applied INBOUND with "traffic-filter inbound acl 3000" on the interface.

Examples:
Request: "create vlan 30 named Sales on HW-SW1"
{"summary": "Create VLAN 30 named Sales on HW-SW1",
 "changes": [{"device": "HW-SW1", "type": "config",
              "commands": ["vlan 30", "description Sales", "quit"],
              "rollback": ["undo vlan 30"]}]}

Request: "set IP 10.0.5.1/24 on GigabitEthernet0/0/1 of HW-R1 and show the interfaces"
{"summary": "Configure 10.0.5.1/24 on GigabitEthernet0/0/1 of HW-R1, then display interfaces",
 "changes": [{"device": "HW-R1", "type": "config",
              "commands": ["interface GigabitEthernet0/0/1", "ip address 10.0.5.1 255.255.255.0", "quit"],
              "rollback": ["interface GigabitEthernet0/0/1", "undo ip address", "quit"]},
             {"device": "HW-R1", "type": "check",
              "commands": ["display ip interface brief"], "rollback": []}]}""",
)
