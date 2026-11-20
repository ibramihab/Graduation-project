"""Configuration conflict detection: compares the plan with what the knowledge base knows.

Only what the plan CHANGES is checked, so configuration that is already on the
devices (and valid) is never reported:
  VLANs       - invalid IDs (not 1-4094), default VLANs that can't be deleted or renamed,
                renaming an existing VLAN, a name already used by another VLAN,
                the same VLAN ID with a different name on another switch
  IPs         - not a valid address, the network/broadcast address of its subnet,
                an address already used by another device or interface,
                a subnet that overlaps another interface of the same device
  Interfaces  - the same setting given two different values in one plan,
                a change to the interface the system uses to manage the device
Returns (errors, warnings).
"""
import ipaddress
import re

from .config_model import MODELLED, read_address, vlan_list
from .state import known_config

DEFAULT_VLANS = {"ios": {1, 1002, 1003, 1004, 1005}, "vrp": {1}}
VLAN_IDS = re.compile(r"\bvlan(?:\s+(?:batch|add))?\s+(\d[\d,\-]*(?:\s+(?:to\s+)?\d[\d,\-]*)*)", re.I)


def check_conflicts(steps, kb) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    devices = {d["name"]: d for d in kb.list_devices()}
    final = {s.name: s.after for s in steps}  # each device after the WHOLE plan
    others = {n: known_config(d, kb) for n, d in devices.items() if n not in final}
    _vlans(steps, final, others, errors, warnings)
    _addresses(steps, devices, final, others, errors, warnings)
    _interfaces(steps, warnings, errors)
    return _unique(errors), _unique(warnings)


# ---------------- VLANs ----------------
def _vlans(steps, final, others, errors, warnings):
    for step in steps:
        for command in step.change.get("commands", []):
            for text in VLAN_IDS.findall(command):
                for number in re.findall(r"\d+", text.lower().replace(" to ", " ")):
                    if not 1 <= int(number) <= 4094:
                        errors.append(f"{step.name}: VLAN {number} in '{command}' is not valid "
                                      "(VLAN IDs go from 1 to 4094)")
        if step.syntax not in MODELLED:
            continue
        before, after = step.before.vlans(), step.after.vlans()
        defaults = DEFAULT_VLANS.get(step.syntax, set())
        negation = step.before.neg
        for command in step.change.get("commands", []):
            match = re.match(rf"{negation}\s+vlan\s+(?:batch\s+)?(.+)$", command.strip().lower())
            for vid in sorted(set(vlan_list(match[1])) & defaults) if match else []:
                errors.append(f"{step.name}: VLAN {vid} is a default VLAN, it can't be deleted")
        for vid in sorted(defaults):
            if after.get(vid) and after.get(vid) != before.get(vid):
                errors.append(f"{step.name}: VLAN {vid} is a default VLAN, it can't be renamed")
        for vid, name in after.items():
            if not name or (name or "").lower() == (before.get(vid) or "").lower():
                continue  # no new name: nothing to compare (same name again = not a conflict)
            if before.get(vid):
                warnings.append(f"{step.name}: conflict - VLAN {vid} already exists named "
                                f"'{before[vid]}'; this plan renames it to '{name}'")
            same = [v for v, n in after.items() if v != vid and n and n.lower() == name.lower()]
            if same:
                warnings.append(f"{step.name}: conflict - the name '{name}' is already used by "
                                f"VLAN {same[0]} on this device")
            for other, config in {**final, **others}.items():
                if other == step.name:
                    continue
                theirs = config.vlans().get(vid)
                if theirs and theirs.lower() != name.lower():
                    warnings.append(f"{step.name}: conflict - VLAN {vid} is called '{theirs}' on {other} "
                                    f"but '{name}' here; the same VLAN ID should mean the same network")


# ---------------- IP addresses ----------------
def _addresses(steps, devices, final, others, errors, warnings):
    book = []  # every address in the network: (device, interface, ip, network)
    for name, config in {**others, **final}.items():
        for interface in config.interfaces():
            book += [(name, interface, ip, net, config.display(f"interface {interface}"))
                     for ip, net, _ in config.addresses(interface)]
    for name, device in devices.items():
        try:
            book.append((name, "management", ipaddress.ip_address(device.get("ip", "")), None, ""))
        except ValueError:
            pass
    new = []
    for step in steps:
        new += [(step, *entry) for entry in _new_addresses(step, errors)]
    book += [(s.name, i, ip, net, i) for s, i, ip, net in new if s.syntax not in MODELLED]

    for step, interface, ip, net in new:
        label = step.after.display(f"interface {interface}") or interface
        if net and net.prefixlen < 31 and ip in (net.network_address, net.broadcast_address):
            kind = "network" if ip == net.network_address else "broadcast"
            errors.append(f"{step.name}: {ip} is the {kind} address of {net}, "
                          f"it can't be used on {label}")
        for device, other, ip2, net2, other_label in book:
            if device == step.name and other in (interface, "management"):
                continue  # the same interface (or its own management address)
            if ip2 == ip:
                where = "its management address" if other == "management" else other_label
                errors.append(f"{step.name}: conflict - {ip} (for {label}) is already used by "
                              f"{device} ({where})")
            elif device == step.name and other != "management" and (
                    (net and ip2 in net) or (net2 and ip in net2)):
                errors.append(f"{step.name}: conflict - {ip}/{net.prefixlen if net else '?'} on {label} "
                              f"overlaps {other_label} ({ip2}) on the same device")


def _new_addresses(step, errors) -> list:
    """[(interface, ip, network)] the step adds. Invalid addresses become errors."""
    found = []
    if step.syntax in MODELLED:
        old = {(i, line) for i in step.before.interfaces() for _, _, line in step.before.addresses(i)}
        for interface, settings in step.after.interfaces().items():
            for setting, line in settings.items():
                if not setting.startswith("ip address") or (interface, line) in old:
                    continue
                words = line.split()
                if len(words) > 2 and not words[2][0].isdigit():
                    continue  # "ip address dhcp" / "negotiated": the address comes from elsewhere
                mask = words[3] if len(words) > 3 and words[3].lower() not in ("secondary", "sub") else None
                try:
                    ip, net = read_address(words[2], mask)
                    found.append((interface, ip, net))
                except (ValueError, IndexError):
                    errors.append(f"{step.name}: '{line}' is not a valid IP address and mask")
        return found
    pattern = (r"set ip (\S+) (\S+)" if step.syntax == "fortios"
               else r"address=(\S+?)(?:\s|$)")
    interface = "?"
    for command in step.change.get("commands", []):
        if match := re.match(r'edit\s+"?([^"]+)"?$', command.strip()):
            interface = match[1].lower()
        if match := re.search(r"interface=(\S+)", command):
            interface = match[1].lower()
        if match := re.search(pattern, command):
            try:
                found.append((interface, *read_address(*match.groups())))
            except ValueError:
                errors.append(f"{step.name}: '{command}' does not contain a valid IP address")
    return found


# ---------------- interfaces ----------------
def _interfaces(steps, warnings, errors):
    seen = {}  # (device, section, setting) -> (step number, line)
    for number, step in enumerate(steps, 1):
        if step.syntax not in MODELLED:
            continue
        old, new = step.before.items(), step.after.items()
        for section, old_line, new_line in step.after.overwritten:
            warnings.append(f"{step.name}: conflict - '{old_line}' and then '{new_line}' on "
                            f"{step.after.display(section)} in the same step: only the last one stays")
        for item in set(old) | set(new):
            section, setting = item
            if section is None or setting is None or old.get(item) == new.get(item):
                continue
            key = (step.name, section, setting)
            if key in seen and seen[key][1] != new.get(item):
                first, line = seen[key]
                errors.append(f"{step.name}: conflict - {step.after.display(section)} is set twice in "
                              f"this plan: '{line or 'removed'}' (step {first}) and "
                              f"'{new.get(item) or 'removed'}' (step {number})")
            seen[key] = (number, new.get(item))
        interface = management_interface_changed(step)
        if interface:
            warnings.append(f"{step.name}: {interface} holds the management address "
                            f"{step.device.get('ip')} that this system uses to reach the device; this "
                            "change could cut the connection (and then the rollback could not be sent)")


def management_interface_changed(step) -> str | None:
    """The name of the interface holding the device's management IP, if this step shuts it,
    re-addresses it, changes its port mode/VLAN or deletes it (that can cut our own access)."""
    address = step.device.get("ip")
    if step.syntax not in MODELLED:
        return None
    old, new = step.before.items(), step.after.items()
    for interface in step.before.interfaces():
        if not any(str(ip) == address for ip, _, _ in step.before.addresses(interface)):
            continue
        section = f"interface {interface}"
        changed = [s for (sec, s) in set(old) | set(new)
                   if sec == section and old.get((sec, s)) != new.get((sec, s))]
        # an IP change is only risky if the management address is gone afterwards
        # (the same IP again, or an extra secondary IP, keeps the device reachable)
        address_kept = interface in step.after.interfaces() and \
            any(str(ip) == address for ip, _, _ in step.after.addresses(interface))
        risky = [s for s in changed if s is None  # the interface is deleted
                 or (s == "shutdown" and (new.get((section, s)) or "").lower() == "shutdown")
                 or (s.startswith("ip address") and not address_kept)
                 or s.startswith(("switchport", "port "))]
        if risky:
            return step.before.display(section)
    return None


def _unique(messages: list[str]) -> list[str]:
    return list(dict.fromkeys(messages))
