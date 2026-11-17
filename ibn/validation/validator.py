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
Advanced checks (each in its own file, they simulate the change on a config model):
  9. rollback.py      - the rollback really undoes every change (and damages nothing)
 10. conflicts.py     - VLAN / IP / interface conflicts with the current network
 11. dependencies.py  - missing prerequisites (VLANs, port modes, ACLs, next hops...)
 12. risk.py          - a risk score 0-100 (LOW / MEDIUM / HIGH / CRITICAL) with reasons
 13. batfish_check.py - (optional) Batfish compares the network before/after the plan:
                        config validity, routing, loops, reachability, ACLs (Cisco IOS)

Result: {"ok": bool, "errors": [...], "warnings": [...],
         "risk": {"score": 0-100, "level": "LOW", "reasons": [...]},
         "batfish": {"status": "PASS" | "WARNING" | "FAIL" | "SKIPPED", "results": [...]}}
Errors block the change. Warnings and the risk are shown to the user before they approve
(a CRITICAL risk does not block: the user decides).

Ideas for later: test the config in a lab (GNS3/EVE-NG) or with Batfish,
ask a second LLM to review.
"""
import re

from ..infrastructure.drivers import DRIVERS
from ..knowledge.graph_analysis import impact
from ..vendors import get_vendor
from .batfish_check import analyze as batfish_analyze
from .conflicts import check_conflicts, management_interface_changed
from .dependencies import check_dependencies
from .risk import assess
from .rollback import check_rollback
from .state import build_steps

# A physical interface written in a command: "Ethernet0/0", "Gi0/1", "fa 0/2", "Serial0/0/0".
# Needs a "/" in the number, so it never matches Loopback5, Tunnel1, Vlan10 or IP addresses.
PHYSICAL_INTERFACE = re.compile(
    r"\b(ethernet|fastethernet|gigabitethernet|tengigabitethernet|serial|eth|et|e|fa|f|"
    r"gig|gi|ge|g|te|se|s)\s?(\d+(?:/\d+)+)", re.IGNORECASE)

# Short names that are not the start of the full name ("GE0/0/1" on Huawei).
ALIASES = {"ge": "gigabitethernet"}


def validate(plan: dict, kb) -> dict:
    errors, warnings = [], []
    ready = []  # config changes that passed the basic checks: (change, device, profile)

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

        ready.append((change, device, profile))
        if not change.get("rollback"):
            warnings.append(f"{name}: no rollback commands, a failure can't be undone automatically")
        for command in change.get("commands", []):
            if re.search(profile.check_commands, command.strip().lower()):
                errors.append(f"{name}: '{command}' is a check command, it can't run in config mode")

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

        # Interface names must exist on the device (if we know its interfaces).
        known = [i.split()[0] for i in device.get("interfaces") or []]
        if known:
            for command in change.get("commands", []) + change.get("rollback", []):
                for kind, number in PHYSICAL_INTERFACE.findall(command):
                    if not _interface_exists(kind, number, known):
                        errors.append(f"{name}: interface '{kind}{number}' does not exist "
                                      f"(it has: {', '.join(known)})")

    findings = _advanced_checks(ready, kb, errors, warnings)
    batfish = _batfish(plan, kb, errors, warnings, findings)
    risk = assess(plan, kb, findings)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "risk": risk, "batfish": batfish}


def _batfish(plan, kb, errors, warnings, findings) -> dict:
    """Pre-deployment analysis with Batfish (optional, see batfish_check.py).
    FAIL -> error (blocks the plan), WARNING -> warning, PASS -> nothing to add."""
    if errors:  # the plan is already rejected: don't spend time on the full analysis
        return {"status": "SKIPPED", "results": [], "reason": "the plan already has errors"}
    result = batfish_analyze(plan, kb)
    for item in result["results"]:
        if item["status"] == "FAIL":
            errors.append(f"Batfish ({item['check']}): {item['message']}")
        elif item["status"] == "WARNING":
            warnings.append(f"Batfish ({item['check']}): {item['message']}")
    findings["batfish_errors"] = sum(r["status"] == "FAIL" for r in result["results"])
    findings["batfish_warnings"] = sum(r["status"] == "WARNING" for r in result["results"])
    return result


def _advanced_checks(ready, kb, errors, warnings) -> dict:
    """Rollback, conflict and dependency checks. Returns how many problems each found
    (the risk score uses these counts)."""
    findings = {"missing_rollback": sum(1 for c, _, _ in ready if not c.get("rollback"))}
    steps = build_steps(ready, kb)
    findings["cut_access"] = sorted({s.name for s in steps if management_interface_changed(s)})
    for kind, check in (("rollback", check_rollback),
                        ("conflict", lambda s: check_conflicts(s, kb)),
                        ("dependency", lambda s: check_dependencies(s, kb))):
        new_errors, new_warnings = check(steps)
        errors += [e for e in new_errors if e not in errors]
        warnings += [w for w in new_warnings if w not in warnings]
        findings[f"{kind}_errors"], findings[f"{kind}_warnings"] = len(new_errors), len(new_warnings)
    return findings


def _interface_exists(kind: str, number: str, known: list[str]) -> bool:
    """'Gi0/1' matches 'GigabitEthernet0/1', 'e0/0' matches 'Ethernet0/0'."""
    kind = ALIASES.get(kind.lower(), kind)
    for name in known:
        match = re.match(r"([A-Za-z-]+)([\d/]+)$", name)
        if match and match[1].lower().startswith(kind.lower()) and match[2] == number:
            return True
    return False
