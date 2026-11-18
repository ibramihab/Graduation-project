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
 12. IP addresses in the commands are valid: each part 0-255, a real mask, and not the
     network or broadcast address of their subnet
 13. the plan does what the user asked: every new IP address the user typed must appear in
     the commands. The AI may not quietly change it (asked for 10.1.1.0, it wrote 10.1.1.1)
 10b. the same for the "door" to the lab: an interface whose subnet holds this PC's own IP
     (e.g. R2 e0/3 192.168.43.2/24 while the PC is 192.168.43.1). Every device is reached
     through it, so cutting it cuts the program off from ALL of them
 15. IP conflicts, with the IPs the knowledge base knows (from "Find links & IPs" or typed):
     the same IP on two devices or two interfaces, a device's management IP reused, and two
     interfaces of ONE device in overlapping subnets (a real Cisco refuses that with
     "% ... overlaps with ..."). Moving an IP inside the same plan ("no ip address" first) is fine
 16. renaming a VLAN that already exists ("vlan 10" + "name Sales" while VLAN 10 is "HR")
     gets a warning. The VLANs we know come from the switch ("Find links & IPs" reads
     "show vlan brief") and from the program's own successful changes after that
 14. the request itself: an IP the user typed that can never work (300.1.1.1, a broken mask,
     or a network/broadcast address given to an interface) is refused in OUR words, whatever
     the AI wrote (see request_problems; the pipeline then doesn't ask the AI again)

Result: {"ok": bool, "errors": [...], "warnings": [...]}
Errors block the change. Warnings are shown to the user before they approve.

Ideas for later: test the config in a lab (GNS3/EVE-NG) or with Batfish,
check for IP conflicts using the knowledge base, ask a second LLM to review.
"""
import ipaddress
import re
import socket

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

# An IP address given to an interface. Examples it finds:
#   "ip address 10.1.1.1 255.255.255.0"   (Cisco IOS, Huawei; Huawei may write "24" as the mask)
#   "ip address 10.1.1.1/24"              (Arista, NX-OS)
#   "set ip 10.1.1.1 255.255.255.0"       (FortiGate)
# "no ip address ..." (removing an IP) and "ip address dhcp" are not checked.
IP_ADDRESS = re.compile(r"^(?:ip address|set ip)\s+(\d[\d.]*)(?:/(\d+)|\s+(\d[\d.]*))?", re.IGNORECASE)


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

        # IP addresses must be real ones (the AI may write 300.1.1.1 or a broken mask).
        for command in change.get("commands", []):
            problem = _ip_problem(command)
            if problem:
                errors.append(f"{name}: '{command}' {problem}")

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
        warnings += _door_warnings(name, device, change.get("commands", []))
        warnings += _vlan_rename_warnings(name, device, change.get("commands", []), kb)
        errors += _management_rollback_errors(name, device, change)

        # Interface names must exist on the device (if we know its interfaces).
        known = [i.split()[0] for i in device.get("interfaces") or []]
        if known:
            for command in change.get("commands", []) + change.get("rollback", []):
                for kind, number in PHYSICAL_INTERFACE.findall(command):
                    if not _interface_exists(kind, number, known):
                        errors.append(f"{name}: interface '{kind}{number}' does not exist "
                                      f"(it has: {', '.join(known)})")

    if plan.get("changes"):
        errors += _changed_values_errors(plan, kb)
        errors += _ip_conflict_errors(plan, kb)

    # The user's own request is wrong: say so ourselves (a small AI may "fix" it with a value of its own).
    problems = request_problems(plan.get("intent", ""))
    if problems:
        errors = [f"Your request: {problem}" for problem in problems]

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def request_problems(text: str) -> list[str]:
    """Mistakes in the user's own words, found without the AI: an IP like 300.1.1.1 or 10.5.5,
    a broken mask, and, when the request sets an interface's IP, a network or broadcast address.
    (In a route or OSPF request a network address like 192.168.5.0/24 is normal, so not there.)"""
    text = text.split("Your previous plan was rejected")[0]  # only the user's words
    sets_interface_ip = (re.search(r"\b(interface|loopback|ip of|ip address)\b", text, re.IGNORECASE)
                         and not re.search(r"\b(route|network|ospf|eigrp|bgp|rip|advertise|access-list|acl|"
                                           r"ping|traceroute)\b", text, re.IGNORECASE))
    problems = []
    # "10.1.1.0/24", "10.5.5.1 with mask 255.0.255.0", "300.1.1.1", "10.5.5"
    found = re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){2,4})(?![\d.])(?:/(\d+)|\s+(?:with\s+)?"
                       r"(?:sub)?(?:net)?mask\s+(\d{1,3}(?:\.\d{1,3}){3}))?", text, re.IGNORECASE)
    for ip, prefix, mask in found:
        if ip.startswith(("255.", "0.")) and not prefix:
            continue  # a mask written on its own
        if ip.count(".") != 3 and not sets_interface_ip:
            continue  # "15.2.4" in "IOS 15.2.4" is a version, not a broken IP
        typed = f"{ip}/{prefix}" if prefix else f"{ip} mask {mask}" if mask else ip
        problem = _ip_problem(f"ip address {ip}/{prefix}" if prefix else f"ip address {ip} {mask}".strip())
        if problem and (sets_interface_ip or "address of" not in problem):
            problems.append(f"{typed} {problem}")
    return problems


def _changed_values_errors(plan: dict, kb) -> list[str]:
    """The IP addresses the user typed must be in the plan, unchanged."""
    # On the AI's second try the request also holds the errors we sent back: keep only the user's words.
    request = plan.get("intent", "").split("Your previous plan was rejected")[0]
    commands = " ".join(c for change in plan["changes"] for c in change.get("commands", []))
    errors = []

    # IP addresses. Skip masks (255.255.255.0, 0.0.0.255) and IPs the network already has
    # ("change sw1's IP from 10.0.1.11 to ..." names the old one, which won't be in the commands).
    ip = r"\b\d{1,3}(?:\.\d{1,3}){3}\b"
    existing = set()
    for device in kb.list_devices():
        existing.add((device.get("ip") or "").strip())
        existing.update(i.split()[1].split("/")[0] for i in device.get("interfaces") or [] if len(i.split()) > 1)
    used = set(re.findall(ip, commands))
    for asked in dict.fromkeys(re.findall(ip, request)):
        if asked.startswith(("255.", "0.")) or asked in existing or asked in used:
            continue
        instead = sorted(u for u in used if u not in existing and not u.startswith(("255.", "0.")))
        errors.append(_changed_value("IP address", asked, instead))
    return errors


def _changed_value(what: str, asked: str, instead: list[str]) -> str:
    used = f" (it uses {', '.join(instead)} instead)" if instead else ""
    return (f"You asked for {what} {asked}, but the plan doesn't use it{used}. The AI must not change "
            f"your values: if {asked} can't be used, the plan must have no changes and say why.")


def _vlan_rename_warnings(name: str, device: dict, commands: list[str], kb) -> list[str]:
    existing = known_vlans(device, kb.get_history(name))
    warnings = []
    for number, new_name in _vlan_names(commands).items():
        if new_name and number in existing and existing[number] and existing[number] != new_name:
            warnings.append(f"{name}: VLAN {number} already exists on {name} as '{existing[number]}': "
                            f"this plan renames it to '{new_name}'")
    return warnings


def known_vlans(device: dict, history: list[dict]) -> dict[str, str]:
    """{"10": "HR"}: what the switch said at "Find links & IPs", then the program's own
    successful changes since then (a failed plan was rolled back, so it doesn't count)."""
    vlans = {}
    for line in device.get("vlans") or []:
        number, _, vlan_name = line.partition(" ")
        vlans[number] = vlan_name
    read_at = device.get("vlans_read_at", "")
    for entry in sorted(history, key=lambda e: e.get("time", "")):
        if entry.get("success") and entry.get("type", "config") == "config" and entry.get("time", "") > read_at:
            for number, vlan_name in _vlan_names(entry.get("commands", []), vlans).items():
                if vlan_name is None:
                    vlans.pop(number, None)  # "no vlan 10"
                else:
                    vlans[number] = vlan_name
    return vlans


def _vlan_names(commands: list[str], before: dict | None = None) -> dict[str, str | None]:
    """What the commands do to VLANs: {"10": "Sales"} (created/renamed), {"10": None} (deleted).
    "vlan 10" then "name Sales" (Cisco, Arista, NX-OS; Huawei may write "description Sales")."""
    result, current = {}, None
    for command in commands:
        line = command.strip()
        created = re.match(r"vlan\s+(\d+)$", line, re.IGNORECASE)
        deleted = re.match(r"(?:no|undo)\s+vlan\s+(\d+)$", line, re.IGNORECASE)
        named = re.match(r"(?:name|description)\s+(.+)$", line, re.IGNORECASE)
        if created:
            current = created[1]
            result.setdefault(current, (before or {}).get(current, ""))  # created, no name yet
        elif deleted:
            result[deleted[1]] = None
            current = None
        elif named and current:
            result[current] = named[1].strip().strip('"')
        elif not line.startswith((" ", "\t")):
            current = None  # another command: we left the VLAN's settings
    return result


def _ip_conflict_errors(plan: dict, kb) -> list[str]:
    """Same IP twice, or overlapping subnets on one device. Works with what real devices give us:
    interfaces with a mask (Cisco: "Ethernet0/0 10.1.2.1/24") or without (other vendors)."""
    known = _known_ips(kb)  # [(device, interface or None, ip, prefix or None)]
    errors = []
    for change in plan["changes"]:
        if change.get("type") == "check":
            continue
        device = change.get("device")
        added, removed = _ips_in_commands(change.get("commands", []))

        def on_same_interface(entry, interface):
            return entry[0] == device and entry[1] and _same_interface(interface, entry[1])

        # "no ip address" on an interface frees its IP (moving an IP in one plan is fine)
        known = [k for k in known if not any(r and on_same_interface(k, r) for r in removed)]
        for interface, ip, prefix, secondary in added:
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                continue  # an invalid IP: the IP check already reports it
            for other_device, other_interface, other_ip, other_prefix in known:
                entry = (other_device, other_interface, other_ip, other_prefix)
                if on_same_interface(entry, interface):
                    continue  # setting the same interface again
                if other_ip == ip and (other_interface or other_device != device):
                    where = f"{other_device} {other_interface}" if other_interface \
                        else f"{other_device} (its management IP)"
                    errors.append(f"{device}: {ip} is already used on {where}")
                elif (other_device == device and other_interface and prefix is not None
                      and other_prefix is not None
                      and ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False).overlaps(
                          ipaddress.IPv4Network(f"{other_ip}/{other_prefix}", strict=False))):
                    errors.append(f"{device}: {ip}/{prefix} on {interface} overlaps with {other_interface} "
                                  f"({other_ip}/{other_prefix}): the device would refuse it")
            if not secondary:  # a new primary IP replaces the interface's old one
                known = [k for k in known if not on_same_interface(k, interface)]
            known.append((device, interface, ip, prefix))
    return errors


def _known_ips(kb) -> list[tuple]:
    """Every IP the network already has: interface IPs, and management IPs not on a known interface."""
    known = []
    for device in kb.list_devices():
        on_interfaces = set()
        for line in device.get("interfaces") or []:
            parts = line.split()
            if len(parts) < 2 or not re.match(r"\d+\.\d+\.\d+\.\d+(/\d+)?$", parts[1]):
                continue  # "unassigned", or no IP
            ip, _, prefix = parts[1].partition("/")
            if ip != "0.0.0.0":
                known.append((device["name"], parts[0], ip, int(prefix) if prefix else None))
                on_interfaces.add(ip)
        management = (device.get("ip") or "").strip()
        if management and management not in on_interfaces:
            known.append((device["name"], None, management, None))
    return known


def _ips_in_commands(commands: list[str]) -> tuple[list[tuple], list[str]]:
    """The IPs the commands give to interfaces, and the interfaces whose IP they remove.
    Cisco / Arista / Huawei:  "interface Ethernet0/1" + "ip address 10.1.1.1 255.255.255.0"
    FortiGate:                'edit "port1"' + "set ip 10.1.1.1 255.255.255.0"
    MikroTik:                 "/ip address add address=10.1.1.1/24 interface=ether1"  """
    added, removed, interface = [], [], None
    for command in commands:
        line = command.strip()
        lower = line.lower()
        opened = re.match(r"int(?:erface)?\s+(\S.*)$", line, re.IGNORECASE) or \
            re.match(r'edit\s+"?([^"\s]+)"?', line, re.IGNORECASE)
        if opened:
            interface = opened[1].replace(" ", "")
            continue
        mikrotik = re.search(r"address=(\d[\d.]*)(?:/(\d+))?.*\binterface=(\S+)", line, re.IGNORECASE)
        if mikrotik:
            added.append((mikrotik[3], mikrotik[1], int(mikrotik[2]) if mikrotik[2] else None, False))
        elif re.match(r"(no|undo) ip address|unset ip\b", lower):
            removed.append(interface)
        elif interface and not lower.startswith("ip address dhcp"):
            found = IP_ADDRESS.match(line)
            if found:
                added.append((interface, found[1], _prefix(found[2] or found[3]), "secondary" in lower))
    return added, removed


def _prefix(mask: str | None) -> int | None:
    """ "255.255.255.0" or "24" -> 24. None if there is no mask or it's broken."""
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen if mask else None
    except ValueError:
        return None


def _ip_problem(command: str) -> str | None:
    """What's wrong with the IP address in this command, or None if it is fine (or has no IP)."""
    found = IP_ADDRESS.match(command.strip())
    if not found:
        return None
    ip, mask = found[1], found[2] or found[3]
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        return f"has an invalid IP address {ip} (4 numbers from 0 to 255)"
    if not mask:
        return None  # no mask written: nothing more to check
    try:
        subnet = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    except ValueError:
        return f"has an invalid mask {mask}"
    # Python also accepts "0.0.0.255" (an ACL wildcard) as /24, but on an interface that's a mistake.
    if "." in mask and str(subnet.netmask) != mask:
        return f"has an invalid mask {mask} (did you mean {subnet.netmask}?)"
    if subnet.prefixlen <= 30:  # /31 and /32 have no network or broadcast address
        if address == subnet.network_address:
            return f"uses {ip}, the network address of {subnet}: it can't be given to an interface"
        if address == subnet.broadcast_address:
            return f"uses {ip}, the broadcast address of {subnet}: it can't be given to an interface"
    return None


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


def local_ips() -> list[str]:
    """This PC's own IPv4 addresses (the program runs here). Empty if they can't be read."""
    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def _door_warnings(name: str, device: dict, commands: list[str]) -> list[str]:
    """Warn when a command would cut the interface that connects this PC to the lab."""
    mine = [ipaddress.IPv4Address(ip) for ip in local_ips() if not ip.startswith("127.")]
    warnings = []
    for line in device.get("interfaces") or []:
        parts = line.split()
        if len(parts) < 2 or "/" not in parts[1] or parts[0] == management_interface(device):
            continue  # no mask saved, or already covered by the management-IP warning
        try:
            subnet = ipaddress.IPv4Network(parts[1], strict=False)
        except ValueError:
            continue
        pc = next((ip for ip in mine if ip in subnet), None)
        if not pc:
            continue
        for command, cmd in _management_lines(commands, parts[0]):
            if re.match(r"shutdown$", cmd) or re.match(r"(no|undo) ip address", cmd) or \
                    (re.match(r"ip address\s+", cmd) and "secondary" not in cmd):
                warnings.append(f"{name}: '{command}' on {parts[0]} can cut the program off from EVERY "
                                f"device: this PC ({pc}) reaches the lab through {name} {parts[0]} "
                                f"({parts[1]}). The rollback won't be able to reach anything.")
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
