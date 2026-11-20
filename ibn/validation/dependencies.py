"""Dependency and precondition checks: does everything the change NEEDS exist?

For each interface the step changes (Cisco-like and Huawei devices):
  - an access VLAN / trunk VLANs / an SVI (interface Vlan10) need that VLAN to exist
  - access settings need the port in access mode, trunk settings need trunk mode
  - an IP address on a switch port needs the port to be routed ("no switchport")
For the device:
  - a static route's next hop must not be its own address
  - an OSPF "network" line should match at least one interface address
For the plan:
  - two connected devices that both get new addresses should share a subnet
(a missing access VLAN, an undefined ACL and a next hop outside every connected subnet
 are checked in validator.py, so each problem is reported only once.)

A VLAN is only reported missing when we really know the device's VLANs (from its
config backup), so VLANs created by hand earlier are not reported by mistake.
Returns (errors, warnings).
"""
from .config_model import MODELLED

MODE_HINT = {"ios": {"access": "switchport mode access", "trunk": "switchport mode trunk",
                     "routed": "no switchport"},
             "vrp": {"access": "port link-type access", "trunk": "port link-type trunk",
                     "routed": "undo portswitch"}}


def check_dependencies(steps, kb) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for step in steps:
        if step.syntax not in MODELLED:
            continue
        for interface in _changed_interfaces(step):
            _interface(step, interface, warnings)
        _routes(step, errors, warnings)
        _ospf(step, warnings)
    _link_subnets(steps, kb, warnings)
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def _changed_interfaces(step) -> list[str]:
    old, new = step.before.items(), step.after.items()
    changed = {sec for (sec, s) in set(old) | set(new)
               if sec and sec.startswith("interface ") and old.get((sec, s)) != new.get((sec, s))}
    return sorted(sec[len("interface "):] for sec in changed if (sec, None) in new)


def _interface(step, interface, warnings):
    after, name = step.after, step.name
    label = after.display(f"interface {interface}")
    hint = MODE_HINT[step.syntax]
    mode = after.mode(interface)
    vlans = after.vlans()

    def need_vlan(vid, why):
        if after.vlans_known and vid not in vlans and vid not in (1, 1002, 1003, 1004, 1005):
            warnings.append(f"{name}: missing prerequisite - VLAN {vid} ({why}) does not exist on the "
                            f"device; create it first (e.g. 'vlan {vid}')")

    access = after.access_vlan(interface)
    if access:
        if mode == "trunk":
            warnings.append(f"{name}: conflict - {label} is a trunk port, so its access VLAN {access} "
                            f"is ignored (use '{hint['access']}' or set the trunk VLANs)")
        elif mode != "access":
            warnings.append(f"{name}: missing prerequisite - {label} gets access VLAN {access} but the "
                            f"port is not set to access mode (add '{hint['access']}')")
        # (a missing access VLAN is warned about in validator.py)

    trunk = after.trunk_vlans(interface)
    if trunk is None or trunk:
        if mode != "trunk":
            warnings.append(f"{name}: missing prerequisite - {label} gets trunk VLANs but the port is "
                            f"not set to trunk mode (add '{hint['trunk']}')")
        for vid in trunk or []:
            need_vlan(vid, f"allowed on trunk {label}")

    if after.addresses(interface) and mode in ("access", "trunk"):
        warnings.append(f"{name}: missing prerequisite - {label} is a switch port ({mode}); "
                        f"add '{hint['routed']}' before giving it an IP address")

    for prefix in ("vlanif", "vlan"):
        if interface.startswith(prefix) and interface[len(prefix):].isdigit():
            need_vlan(int(interface[len(prefix):]), f"used by {label}")
            break

    # (an access list that is used but not defined is warned about in validator.py)


def _all_addresses(config):
    return [(ip, net) for i in config.interfaces() for ip, net, _ in config.addresses(i)]


def _routes(step, errors, warnings):
    before_routes = {line for _, _, line in step.before.routes()}
    addresses = _all_addresses(step.after)
    own = {ip for ip, _ in addresses}
    for network, hop, line in step.after.routes():
        if line in before_routes:
            continue
        if hop in own:
            errors.append(f"{step.name}: '{line}' uses the device's own address {hop} as next hop")
        # (a next hop outside every connected subnet is warned about in validator.py)


def _ospf(step, warnings):
    before = {line for _, line in step.before.ospf_networks()}
    own = [ip for ip, _ in _all_addresses(step.after)]
    if not own:
        return
    for network, line in step.after.ospf_networks():
        if line not in before and not any(ip in network for ip in own):
            warnings.append(f"{step.name}: '{line}' matches none of the device's interface addresses, "
                            "so OSPF will not run on any interface for it")


def _link_subnets(steps, kb, warnings):
    """If both ends of a link get new addresses in this plan, they should share a subnet."""
    new = {}
    for step in steps:
        if step.syntax in MODELLED:
            old = set(_all_addresses(step.before))
            new.setdefault(step.name, set()).update(
                net for ip, net in _all_addresses(step.after) if net and (ip, net) not in old)
    for link in kb.list_links():
        a, b = new.get(link["a"]), new.get(link["b"])
        if a and b and not a & b:
            warnings.append(f"{link['a']} and {link['b']} are connected, but their new addresses are in "
                            f"different subnets ({', '.join(map(str, sorted(a)))} vs "
                            f"{', '.join(map(str, sorted(b)))}); check they are on the right link")

