"""Rollback validation: does the rollback really undo the change?

For Cisco-like and Huawei devices we SIMULATE it on the config model:
    before --commands--> after --rollback--> undone
and compare "undone" with "before", item by item. Every difference is explained:
    - something the change added is still there          -> "does not remove / undo"
    - something the change replaced is not put back       -> "does not restore"
    - something that existed BEFORE the change is deleted -> error: the rollback itself
      would damage the network (e.g. "no vlan 10" when VLAN 10 was already in use)
Plus vendor rules: the right "no"/"undo" word, no check commands, no deleting a
physical port, FortiGate blocks closed with "end", MikroTik "add" undone with "remove".

Returns (errors, warnings). An EMPTY rollback is reported by validator.py (as before).
"""
import re

from .config_model import MODELLED, NEGATION, is_physical


def check_rollback(steps) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for step in steps:
        rollback = step.change.get("rollback") or []
        if not rollback:
            continue
        _vendor_rules(step, rollback, errors)
        if step.syntax in MODELLED:
            _simulate(step, rollback, errors, warnings)
        elif step.syntax == "fortios":
            _fortigate(step, rollback, errors, warnings)
        elif step.syntax == "routeros":
            _mikrotik(step, rollback, warnings)
    return errors, warnings


def _vendor_rules(step, rollback, errors):
    name = step.name
    for command in rollback:
        low = command.strip().lower()
        if re.search(step.profile.check_commands, low):
            errors.append(f"{name}: rollback line '{command}' is a check command, "
                          "it can't run in config mode")
        if step.syntax in MODELLED:
            right = NEGATION[step.syntax]
            wrong = "no" if right == "undo" else "undo"
            if low.startswith(wrong + " "):
                errors.append(f"{name}: rollback line '{command}' uses '{wrong}', "
                              f"but {step.profile.description} uses '{right}'")
            match = re.match(rf"{right}\s+interface\s+(\S+(?:\s*[\d/.:]+)?)$", low)
            if match and is_physical(match[1]):
                errors.append(f"{name}: rollback line '{command}' tries to delete a physical port; "
                              "undo its settings instead (it can't be deleted, so the rollback would fail)")


def _simulate(step, rollback, errors, warnings):
    before, after = step.before, step.after
    undone = after.copy().apply(rollback)
    old, new, back = before.items(), after.items(), undone.items()
    neg = before.neg

    for item in sorted(set(old) | set(new), key=str):
        if old.get(item) == new.get(item):
            continue  # the change did not touch it
        section, setting = item
        was, now, left = old.get(item), new.get(item), back.get(item)
        if _same(was, left, neg):
            continue  # undone correctly
        where = f" on {before.display(section) or after.display(section)}" if section else ""

        if setting is None:  # a whole section (VLAN, interface, ACL...)
            if was is None and left is not None:
                if _physical_port(section):
                    continue  # a real port "appears" only because we didn't know it: nothing to remove
                warnings.append(f"{step.name}: rollback does not remove '{now}' that the change creates "
                                f"(add '{neg} {now}')")
            elif now is None and left is None:
                warnings.append(f"{step.name}: rollback does not re-create '{was}' that the change deletes")
            continue
        known = was is not None or before.complete
        if was is None and left == now:
            warnings.append(f"{step.name}: rollback does not undo '{now}'{where}"
                            + (f" (add '{neg} {now}')" if not now.lower().startswith(neg + " ") else ""))
        elif was is not None and left is None and (section, None) not in back and section:
            pass  # the whole section is gone: reported below as one message
        elif was is not None:
            warnings.append(f"{step.name}: rollback does not restore '{was}'{where} "
                            f"(after the rollback it would be: '{left or 'nothing'}')")
        elif known and left is not None:
            warnings.append(f"{step.name}: rollback leaves '{left}'{where}, which was not there before")

    # Things that existed BEFORE the change, that the change KEPT, but the rollback deletes = damage.
    for (section, setting), line in old.items():
        if setting is None and (section, None) in new and (section, None) not in back \
                and not _physical_port(section):  # (deleting a port is reported by _vendor_rules)
            errors.append(f"{step.name}: rollback deletes '{line}', which existed BEFORE this change; "
                          f"if the change fails, the rollback would remove it (only undo what the plan adds)")


def _same(a: str | None, b: str | None, neg: str) -> bool:
    """Two config lines that mean the same thing:
    'no shutdown' = nothing set, and 'ip address 10.0.0.1' (mask unknown) = 'ip address 10.0.0.1 255.0.0.0'."""
    a, b = (" ".join(x.lower().split()) if x else None for x in (a, b))
    if a == b or {a, b} == {None, f"{neg} shutdown"}:
        return True
    if a and b and a.startswith("ip address") and b.startswith("ip address"):
        x, y = a.split(), b.split()
        return len(x) > 2 and len(y) > 2 and x[2] == y[2] and (len(x) == 3 or len(y) == 3)
    return False


def _physical_port(section: str) -> bool:
    return section.startswith("interface ") and is_physical(section[len("interface "):])


def _fortigate(step, rollback, errors, warnings):
    """FortiOS: every "config" block must be closed with "end", and an entry the change
    creates in a table ("edit 1001") should be deleted or edited back."""
    opened = sum(1 for c in rollback if c.strip().lower().startswith("config "))
    closed = sum(1 for c in rollback if c.strip().lower() == "end")
    if opened != closed:
        errors.append(f"{step.name}: rollback opens {opened} 'config' block(s) but closes {closed} "
                      "with 'end'; the firewall would be left inside a block")
    text = " ".join(c.strip().lower() for c in rollback)
    for command in step.change.get("commands", []):
        match = re.match(r'edit\s+"?([^"]+)"?$', command.strip().lower())
        if match and match[1] not in text:
            warnings.append(f"{step.name}: rollback never mentions entry '{match[1]}' that the change "
                            f"edits (add 'delete {match[1]}' or edit it back)")


def _mikrotik(step, rollback, warnings):
    """RouterOS: '/ip address add ...' should be undone by '/ip address remove ...'."""
    undo_paths = {m[1].lower() for c in rollback if (m := re.match(r"(.*?)\s+remove\b", c.strip()))}
    for command in step.change.get("commands", []):
        if match := re.match(r"(.*?)\s+add\b", command.strip()):
            path = match[1]
            if path.lower() not in undo_paths:
                warnings.append(f"{step.name}: rollback has no '{path} remove ...' for '{command}'")
