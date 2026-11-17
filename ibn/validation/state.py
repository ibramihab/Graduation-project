"""What does a device look like NOW? Built from what the knowledge base knows:

  1. last_config  - the config backup the control layer saves before every change
  2. history      - the changes this system applied after that backup
  3. interfaces   - names + IPs read by "Find links" (or typed by hand)

Then each step of the plan gets its BEFORE and AFTER model (a plan can change the
same device twice, so step 2 starts from step 1's "after").
"""
from dataclasses import dataclass

from .config_model import Config, canonical, syntax_of


@dataclass
class Step:
    """One config change of the plan, ready for the advanced checks."""
    change: dict
    device: dict
    profile: object       # the VendorProfile
    syntax: str           # "ios", "vrp", "fortios", "routeros"
    before: Config
    after: Config

    @property
    def name(self) -> str:
        return self.device["name"]


def known_config(device: dict, kb) -> Config:
    config = Config(syntax_of(device.get("vendor")))
    backup = device.get("last_config") or ""
    if backup:
        config.apply(backup.splitlines())
        config.complete = True
        config.vlans_known = any(k.startswith("vlan ") and k != "vlan 1" for k in config.sections)
    for commands in _applied_after_backup(device, kb, bool(backup)):
        config.apply(commands)
    _add_interface_list(config, device.get("interfaces") or [])
    return config


def _applied_after_backup(device, kb, has_backup) -> list[list[str]]:
    """Commands of the changes that really reached the device (no failures, no dry runs).
    The backup is saved just before the LAST applied change, so with a backup only that
    last change is missing from it."""
    applied = []
    for entry in kb.get_history(device["name"]):
        if entry.get("type", "config") != "config":
            continue
        outputs = [r.get("output", "") for r in entry.get("results", [])]
        if any(str(o).startswith("DRY RUN") for o in outputs):
            continue  # nothing was really sent
        applied.append(entry.get("commands", []) if entry.get("success") else None)
    if has_backup:
        applied = applied[-1:]  # only the newest one (if it worked)
    return [c for c in applied if c]


def _add_interface_list(config: Config, interfaces: list[str]) -> None:
    """'Ethernet0/0 10.1.2.1' entries: the interface exists and has this IP (the real one,
    read from the device, so it wins over older history)."""
    for entry in interfaces:
        parts = entry.split()
        if not parts:
            continue
        key = "interface " + canonical(parts[0])
        settings = config.sections.setdefault(key, {})
        config.names.setdefault(key, "interface " + parts[0])
        if len(parts) > 1 and parts[1][:1].isdigit():
            address = parts[1].split("/")[0]
            if any(str(ip) == address for ip, _, _ in config.addresses(key[len("interface "):])):
                continue  # the backup already has it, with its mask
            settings["ip address"] = "ip address " + parts[1].replace("/", " ")


def build_steps(ready: list, kb) -> list[Step]:
    """ready = [(change, device, profile)] for the config changes that passed the basic checks."""
    states, steps = {}, []
    for change, device, profile in ready:
        name = device["name"]
        if name not in states:
            states[name] = known_config(device, kb)
        before = states[name]
        after = before.copy().apply(change.get("commands", []))
        steps.append(Step(change, device, profile, syntax_of(device.get("vendor")), before, after))
        states[name] = after
    return steps
