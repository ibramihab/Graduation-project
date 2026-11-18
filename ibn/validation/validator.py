"""Validation layer: checks the AI's plan BEFORE anything touches a device.

The AI can make mistakes, so we never trust it blindly. Checks:
  1. the device exists in the knowledge base
  2. we have a driver for its vendor
  3. the device is reachable (not "down")
  4. there are commands and a rollback
  5. no dangerous commands (the vendor's "blocked" list in ibn/vendors/)
  6. "check" steps only contain read-only commands (ping, show, display...), and
     "config" steps don't contain them (they only work outside config mode)
  7. physical interfaces in the commands (Ethernet0/0, Gi0/1...) really exist
     on the device (we know them from "Find links & IPs")
  8. a risky change (shutdown, ACL...) on a device that is a single point of failure
     gets an extra warning saying which parts of the network would be cut off
  9. VLAN numbers in the commands are valid (1-4094)
 10. a change on the interface that holds the device's management IP (shutdown, new IP,
     no IP) gets a warning: it would cut the program's own connection to the device
 11. the rollback must not cut the device off either: it can't delete the management
     interface, and if the plan changes the management IP, the rollback must put the old one back

Result: {"ok": bool, "errors": [...], "warnings": [...]}
Errors block the change. Warnings are shown to the user before they approve.

Ideas for later: test the config in a lab (GNS3/EVE-NG) or with Batfish,
check for IP conflicts using the knowledge base, ask a second LLM to review.
"""
import ipaddress
import re

from ..infrastructure.drivers import DRIVERS
from ..knowledge.graph_analysis import impact
from ..vendors import get_vendor

# A physical interface written in a command: "Ethernet0/0", "Gi0/1", "fa 0/2", "Serial0/0/0".
# Needs a "/" in the number, so it never matches Loopback5, Tunnel1, Vlan10 or IP addresses.
PHYSICAL_INTERFACE = re.compile(
    r"\b(ethernet|fastethernet|gigabitethernet|tengigabitethernet|serial|eth|et|e|fa|f|"
    r"gig|gi|ge|g|te|se|s)\s?(\d+(?:/\d+)+)", re.IGNORECASE)

# Short names that are not the start of the full name ("GE0/0/1" on Huawei).
ALIASES = {"ge": "gigabitethernet"}

# VLAN numbers in a command. Examples it finds:
#   "vlan 10"                              -> 10
#   "switchport access vlan 20"            -> 20
#   "switchport trunk allowed vlan add 30" -> 30   (also "remove" / "except")
#   "switchport trunk allowed vlan 10,20-30" -> 10, 20, 30
#   "vlan batch 10 to 20" (Huawei)         -> 10, 20
#   "set vlanid 40" (FortiGate), "encapsulation dot1Q 50" (sub-interface)
# It stops at the first word that is not part of the list, so
# "spanning-tree vlan 10 priority 4096" only gives 10.
VLAN_LIST = re.compile(
    r"\b(?:vlan(?:id)?|dot1q)\s+(?:(?:add|remove|except|batch)\s+)?"
    r"(\d+(?:\s*(?:,|-|\s|to)\s*\d+)*)", re.IGNORECASE)


def validate(plan: dict, kb) -> dict:
    errors, warnings = [], []

    if not plan.get("changes"):
        errors.append("The plan has no changes. " + plan.get("summary", ""))

    for change in plan.get("changes", []):
        name = change.get("device", "?")
        device = kb.get_device(name)
        if not device:
            errors.append(f"{name}: device is not in the knowledge base")
            continue
        vendor = device.get("vendor")
        profile = get_vendor(vendor)
        if vendor not in DRIVERS or not profile:
            errors.append(f"{name}: no driver for vendor '{vendor}'")
            continue
        if device.get("state") == "down":
            errors.append(f"{name}: device is down (not answering ping)")
        if not change.get("commands"):
            errors.append(f"{name}: no commands")

        if change.get("type") == "check":
            for command in change.get("commands", []):
                line = command.strip().lower()
                # "show ... | redirect flash:x" would write a file, so pipes like that are refused
                if not re.search(profile.check_commands, line) or re.search(r"\|\s*(redirect|tee|append)", line):
                    errors.append(f"{name}: '{command}' is not a read-only check command")
            continue  # read-only: no rollback or dangerous-command checks needed

        if not change.get("rollback"):
            warnings.append(f"{name}: no rollback commands, a failure can't be undone automatically")
        for command in change.get("commands", []):
            if re.search(profile.check_commands, command.strip().lower()):
                errors.append(f"{name}: '{command}' is a check command, it can't run in config mode")

        # VLAN numbers must be 1-4094 (the AI may write "vlan 5000" without noticing).
        for command in change.get("commands", []):
            numbers = [n for found in VLAN_LIST.findall(command) for n in re.findall(r"\d+", found)]
            for number in numbers:
                if not 1 <= int(number) <= 4094:
                    errors.append(f"{name}: '{command}' has an invalid VLAN number "
                                  f"{number} (must be 1-4094)")

        # Dangerous commands are blocked everywhere, even inside the rollback.
        for command in change.get("commands", []) + change.get("rollback", []):
            for pattern, reason in profile.blocked:
                if re.search(pattern, command.strip().lower()):
                    errors.append(f"{name}: '{command}' is blocked ({reason})")
        # Warnings only for the real commands (a rollback is SUPPOSED to remove things).
        risky = False
        for command in change.get("commands", []):
            for pattern, reason in profile.warn:
                if re.search(pattern, command.strip().lower()):
                    warnings.append(f"{name}: '{command}' {reason}")
                    risky = True
        # Risky change on a single point of failure? Say what would be cut off.
        if risky:
            groups = impact(kb, name)
            if groups:
                warnings.append(f"{name} is a single point of failure: if this change breaks it, "
                                "the network splits into " + "  |  ".join(", ".join(g) for g in groups))

        # Would this change cut the program off from the device? (its management interface)
        warnings += _management_warnings(name, device, change.get("commands", []))
        errors += _management_rollback_errors(name, device, change)

        # Interface names must exist on the device (if we know its interfaces).
        known = [i.split()[0] for i in device.get("interfaces") or []]
        if known:
            for command in change.get("commands", []) + change.get("rollback", []):
                for kind, number in PHYSICAL_INTERFACE.findall(command):
                    if not _interface_exists(kind, number, known):
                        errors.append(f"{name}: interface '{kind}{number}' does not exist "
                                      f"(it has: {', '.join(known)})")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _management_warnings(name: str, device: dict, commands: list[str]) -> list[str]:
    """The program reaches the device on ONE IP (device["ip"]). If a command turns off or
    changes the interface that holds that IP, we lose the device and the rollback can't reach it."""
    management_ip = (device.get("ip") or "").strip()  # "  10.0.1.11" typed with spaces is the same IP
    interface = management_interface(device)
    if not interface:
        return []  # we don't know it (no interfaces saved, or the IP is not on any of them)

    warnings = []
    for command, line in _management_lines(commands, interface):
        new_ip = re.match(r"ip address\s+(\S+)", line)
        if re.match(r"shutdown$", line) or re.match(r"(no|undo) ip address", line):
            warnings.append(f"{name}: '{command}' on {interface} cuts the program's connection "
                            f"to {name} (its management IP {management_ip} is on that interface). "
                            "The rollback won't be able to reach it.")
        elif new_ip and new_ip[1] != management_ip and "secondary" not in line:
            warnings.append(f"{name}: '{command}' changes the management IP of {name} "
                            f"({management_ip} on {interface}). After applying, the program checks "
                            "that the device answers on the new IP and then uses it; if it doesn't "
                            "answer, the change is reported as failed.")
    return warnings


def _management_rollback_errors(name: str, device: dict, change: dict) -> list[str]:
    """A wrong rollback can be worse than the change: the AI once "undid" a new management IP
    with 'no interface Vlan1', which would leave the device with no way in at all."""
    interface = management_interface(device)
    if not interface:
        return []
    rollback = change.get("rollback", [])
    errors = []

    # 1. The rollback must never delete the management interface.
    for command in rollback:
        deleted = re.match(r"(?:no|undo)\s+int(?:erface)?\s+(.+)", command.strip().lower())
        if deleted and _same_interface(deleted[1], interface):
            errors.append(f"{name}: the rollback '{command}' deletes {interface}, the interface the "
                          "program uses to reach the device")

    # 2. If the plan gives the management interface a new IP, the rollback must put the old one back.
    if new_management_ip(device, change.get("commands", [])):
        old_ip = (device.get("ip") or "").strip()
        restored = any(re.match(rf"ip address\s+{re.escape(old_ip)}\s", line + " ")
                       for _, line in _management_lines(rollback, interface))
        if not restored:
            errors.append(f"{name}: the rollback must put the management IP back: "
                          f"'interface {interface}' then 'ip address {old_ip} {_old_mask(device, interface)}'")
    return errors


def _old_mask(device: dict, interface: str) -> str:
    """The management interface's mask as "255.255.255.0", from its saved line "Vlan1 10.0.1.11/24"."""
    for line in device.get("interfaces") or []:
        parts = line.split()
        if parts[0] == interface and "/" in parts[-1]:
            return str(ipaddress.IPv4Network(f"0.0.0.0/{parts[-1].split('/')[1]}").netmask)
    return "<mask>"


def management_interface(device: dict) -> str | None:
    """The interface that holds the IP the program uses to reach the device, e.g. "Vlan1".
    Interfaces are saved like "Vlan1 10.0.1.11/24". None if we don't know it."""
    management_ip = (device.get("ip") or "").strip()
    for interface in device.get("interfaces") or []:
        parts = interface.split()
        if len(parts) > 1 and parts[1].split("/")[0] == management_ip:
            return parts[0]
    return None


def new_management_ip(device: dict, commands: list[str]) -> tuple[str, int] | None:
    """If the commands give the management interface a NEW IP, return (ip, prefix length),
    e.g. ("10.0.1.50", 24). Used by the Control layer to follow the device to its new IP."""
    interface = management_interface(device)
    if not interface:
        return None
    for _, line in _management_lines(commands, interface):
        found = re.match(r"ip address\s+(\S+)\s+(\S+)", line)  # "ip address 10.0.1.50 255.255.255.0"
        if found and "secondary" not in line and found[1] != (device.get("ip") or "").strip():
            try:  # the mask can be "255.255.255.0" (Cisco) or "24" (Huawei)
                prefix = ipaddress.IPv4Network(f"0.0.0.0/{found[2]}").prefixlen
                return str(ipaddress.IPv4Address(found[1])), prefix
            except ValueError:
                return None  # not a valid IP or mask: don't follow it
    return None


def _management_lines(commands: list[str], interface: str):
    """The settings written INSIDE the management interface, as (command, lower-case line).
    "interface Vlan1" opens it; the next "interface ..." line closes it."""
    inside = False
    for command in commands:
        line = command.strip().lower()
        opened = re.match(r"int(?:erface)?\s+(.+)", line)
        if opened:
            inside = _same_interface(opened[1], interface)
        elif inside:
            yield command, line


def _same_interface(written: str, real: str) -> bool:
    """'vlan 1' is 'Vlan1', 'e0/0' is 'Ethernet0/0', 'gi0/1' is 'GigabitEthernet0/1'."""
    a = re.match(r"([a-z-]+)\s*([\d/.]+)$", written.strip().lower())
    b = re.match(r"([a-z-]+)\s*([\d/.]+)$", real.strip().lower())
    if not a or not b:
        return False
    kind = ALIASES.get(a[1], a[1])
    return b[1].startswith(kind) and a[2] == b[2]


def _interface_exists(kind: str, number: str, known: list[str]) -> bool:
    """'Gi0/1' matches 'GigabitEthernet0/1', 'e0/0' matches 'Ethernet0/0'."""
    kind = ALIASES.get(kind.lower(), kind)
    for name in known:
        match = re.match(r"([A-Za-z-]+)([\d/]+)$", name)
        if match and match[1].lower().startswith(kind.lower()) and match[2] == number:
            return True
    return False
