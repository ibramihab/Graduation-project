"""A vendor PROFILE: everything the system needs to know about one kind of device.

Each vendor has ONE folder with everything about it (ibn/vendors/cisco_ios/, huawei/...):
    profile.py      the PROFILE below; every layer reads it:
        intent      -> ai_hints (rules + examples for the AI), wrapper_lines (lines to clean)
        validation  -> blocked, warn, check_commands, config_commands (syntax)
        drivers     -> netmiko_type, show_config, show_interfaces, parse_interfaces,
                       error_markers, neighbors
        control     -> verify_failed (how a failed post-validation check looks)
    examples.json   (optional) solved requests: the AI's knowledge for RAG (ibn/intent/rag/)

To add a vendor: copy a vendor folder, change the values in profile.py, and add it to the
list in vendors/__init__.py. Nothing else in the project needs to change.
"""
from collections.abc import Callable
from dataclasses import dataclass, field


def two_column_interfaces(output: str) -> list[str]:
    """Read a table whose first two columns are interface + IP (Cisco, Huawei, Arista):
        "Ethernet0/0     10.1.2.1     YES manual up  up"   -> "Ethernet0/0 10.1.2.1"
        "GigabitEthernet0/0/1  10.0.5.1/24  up  up"        -> "GigabitEthernet0/0/1 10.0.5.1"
    Header and comment lines are skipped (their first word doesn't end with a digit)."""
    interfaces = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0][-1].isdigit():
            interfaces.append(f"{parts[0]} {parts[1].split('/')[0]}")
    return interfaces


def vlan_table(output: str) -> list[str]:
    """Read "show vlan brief" (Cisco IOS, NX-OS, Arista): number + name of each VLAN.
        "10   HR                               active    Et0/1"  -> "10 HR"
    Lines that don't start with a VLAN number (headers, "----", ports on a 2nd line) are skipped."""
    vlans = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            vlans.append(f"{parts[0]} {parts[1]}")
    return vlans


@dataclass
class VendorProfile:
    name: str                        # the "vendor" value of a device, e.g. "cisco_ios"
    description: str                 # human name, also shown to the AI, e.g. "Cisco IOS"

    # ---- infrastructure (how the driver talks to it) ----
    netmiko_type: str = ""           # Netmiko device type ("" = no SSH/Telnet driver)
    show_config: str = ""            # prints the running config (backup before changes)
    show_interfaces: str = ""        # lists interfaces and their IPs ("" = can't)
    parse_interfaces: Callable[[str], list[str]] = two_column_interfaces
    neighbors: str = ""              # how to find neighbors: "cdp" ("" = not supported yet)
    show_vlans: str = ""             # lists the VLANs of a switch ("" = can't)
    parse_vlans: Callable[[str], list[str]] = vlan_table  # -> ["10 HR", "20 Sales"]
    error_markers: list[str] = field(default_factory=list)  # text = "command rejected"

    # ---- validation (safety rules) ----
    check_commands: str = r"^(show|ping|traceroute)\b"  # regex: read-only commands
    blocked: list[tuple[str, str]] = field(default_factory=list)  # (regex, reason): never allowed
    warn: list[tuple[str, str]] = field(default_factory=list)     # (regex, reason): look twice
    # Syntax (pre-validation): regex of the config commands this vendor knows, matched on
    # each command without a leading "no". Not matching = unknown or misspelled command.
    # "" = no syntax list yet for this vendor: the check is skipped.
    config_commands: str = ""

    # ---- control (post-validation: did the change really work?) ----
    # regex, searched in the lowercase output of a "verify" command: a match = FAILED.
    # The defaults catch a ping that got no reply on every common vendor:
    #   Cisco "Success rate is 0 percent", Huawei/Nexus/Linux "100% packet loss",
    #   MikroTik "packet-loss=100%".
    verify_failed: list[str] = field(default_factory=lambda: [
        r"success rate is 0 percent", r"\b100(\.0+)?% packet loss", r"packet-loss=100%"])

    # ---- intent (the AI) ----
    wrapper_lines: set[str] = field(default_factory=set)  # added by the driver itself: removed
    ai_hints: str = ""               # vendor rules + worked examples for the AI
