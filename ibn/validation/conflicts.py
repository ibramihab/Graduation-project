"""Configuration conflict detection: compares the plan with what the knowledge base knows.

Only what the plan CHANGES is checked, so configuration that is already on the
devices (and valid) is never reported:
  VLANs       - default VLANs that can't be deleted or renamed,
                a name already used by another VLAN,
                the same VLAN ID with a different name on another switch
  Interfaces  - the same setting given two different values in one plan
(VLAN numbers, renaming a VLAN, IP addresses and the management interface are checked
 in validator.py, so each problem is reported only once.)
Returns (errors, warnings).
"""
import re

from .config_model import MODELLED, vlan_list
from .state import known_config

DEFAULT_VLANS = {"ios": {1, 1002, 1003, 1004, 1005}, "vrp": {1}}


def check_conflicts(steps, kb) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    devices = {d["name"]: d for d in kb.list_devices()}
    final = {s.name: s.after for s in steps}  # each device after the WHOLE plan
    others = {n: known_config(d, kb) for n, d in devices.items() if n not in final}
    _vlans(steps, final, others, errors, warnings)
    _interfaces(steps, warnings, errors)
    return _unique(errors), _unique(warnings)


# ---------------- VLANs ----------------
def _vlans(steps, final, others, errors, warnings):
    # (VLAN numbers 1-4094 and renaming an existing VLAN are checked in validator.py)
    for step in steps:
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


# (IP addresses: invalid values and conflicts are checked in validator.py)


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
        # (a change on the management interface is warned about in validator.py; the risk
        #  score still uses management_interface_changed below)


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
