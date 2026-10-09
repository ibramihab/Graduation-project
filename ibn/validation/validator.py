"""Validation layer: checks the AI's plan BEFORE anything touches a device.

The AI can make mistakes, so we never trust it blindly. Checks:
  1. the device exists in the knowledge base
  2. we have a driver for its vendor
  3. the device is reachable (not "down")
  4. there are commands and a rollback
  5. no dangerous commands (rules.py)
  6. "check" steps only contain read-only commands (ping, show...), and
     "config" steps don't contain them (they only work outside config mode)

Result: {"ok": bool, "errors": [...], "warnings": [...]}
Errors block the change. Warnings are shown to the user before they approve.

Ideas for later: test the config in a lab (GNS3/EVE-NG) or with Batfish,
check for IP conflicts using the knowledge base, ask a second LLM to review.
"""
import re

from ..infrastructure.drivers import DRIVERS
from .rules import BLOCKED, CHECK_ALLOWED, WARN


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
        if vendor not in DRIVERS:
            errors.append(f"{name}: no driver for vendor '{vendor}'")
        if device.get("state") == "down":
            errors.append(f"{name}: device is down (not answering ping)")
        if not change.get("commands"):
            errors.append(f"{name}: no commands")

        if change.get("type") == "check":
            for command in change.get("commands", []):
                line = command.strip().lower()
                # "show ... | redirect flash:x" would write a file, so pipes like that are refused
                if not re.search(CHECK_ALLOWED, line) or re.search(r"\|\s*(redirect|tee|append)", line):
                    errors.append(f"{name}: '{command}' is not a read-only check command")
            continue  # read-only: no rollback or dangerous-command checks needed

        if not change.get("rollback"):
            warnings.append(f"{name}: no rollback commands, a failure can't be undone automatically")
        for command in change.get("commands", []):
            if re.search(CHECK_ALLOWED, command.strip().lower()):
                errors.append(f"{name}: '{command}' is a check command, it can't run in config mode")

        # Dangerous commands are blocked everywhere, even inside the rollback.
        for command in change.get("commands", []) + change.get("rollback", []):
            for pattern, reason in BLOCKED.get(vendor, BLOCKED["default"]):
                if re.search(pattern, command.strip().lower()):
                    errors.append(f"{name}: '{command}' is blocked ({reason})")
        # Warnings only for the real commands (a rollback is SUPPOSED to remove things).
        for command in change.get("commands", []):
            for pattern, reason in WARN:
                if re.search(pattern, command.strip().lower()):
                    warnings.append(f"{name}: '{command}' {reason}")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
