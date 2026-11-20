"""A small MODEL of a device's configuration, used by the advanced checks.

We read config lines (from the saved backup, the change history or the AI's plan)
and remember what they set, so the validation can compare three moments:

    before  = the device now (as far as the knowledge base knows)
    after   = before + the plan's commands
    undone  = after + the rollback commands      -> should be the same as "before"

The model is stored as SECTIONS (an interface, a VLAN, an ACL, "router ospf 1"...)
holding SETTINGS, plus top-level lines (ip route, hostname...):

    sections = {"interface ethernet0/1": {"description": "description Users",
                                          "switchport access vlan": "switchport access vlan 10"},
                "vlan 10": {"name": "name Sales"}}
    top      = {"ip route 0.0.0.0 0.0.0.0 10.0.0.1": "ip route 0.0.0.0 0.0.0.0 10.0.0.1"}

It understands the Cisco-like CLI ("ios": Cisco IOS, NX-OS, Arista, simulated) and
Huawei VRP ("vrp", which says "undo" instead of "no"). FortiGate and MikroTik write
their config very differently, so for them only a few simple checks run.
"""
import ipaddress
import re
from copy import deepcopy

# Which CLI "family" a vendor writes. Every vendor not listed here is Cisco-like ("ios").
SYNTAX = {"huawei": "vrp", "fortigate": "fortios", "mikrotik_routeros": "routeros"}
MODELLED = ("ios", "vrp")             # the families this model understands line by line
NEGATION = {"ios": "no", "vrp": "undo"}

EXITS = {"exit", "quit", "end", "return", "!", "#"}  # lines that leave a section

# Commands that always run at the top level. Typing one inside an interface leaves it.
TOP_LEVEL = re.compile(
    r"^(ip route|ipv6 route|ip route-static|hostname|sysname|access-list|username|ip domain|"
    r"ip name-server|ip default-gateway|ntp|snmp-server|snmp-agent|logging|banner|vtp|"
    r"ip routing|ip dhcp|ip nat (inside|outside) source|spanning-tree (mode|vlan)|stp mode|"
    r"crypto|aaa|service|enable|cdp run|lldp run|vlan batch)\b")

# Settings that REPLACE their old value (e.g. a new "description" replaces the old one).
# Every other line ADDS to the list (e.g. "network ..." lines under "router ospf").
REPLACING = sorted([
    "ip address", "ipv6 address", "description", "name", "shutdown", "switchport",
    "switchport mode", "switchport access vlan", "switchport trunk allowed vlan",
    "switchport trunk native vlan", "switchport trunk encapsulation", "switchport voice vlan",
    "port link-type", "port default vlan", "port trunk allow-pass vlan", "port trunk pvid vlan",
    "portswitch", "speed", "duplex", "mtu", "bandwidth", "ip ospf cost", "ip ospf priority",
    "encapsulation dot1q", "channel-group", "router-id",
    "hostname", "sysname", "ip default-gateway", "ip domain-name", "ip domain name",
    "spanning-tree mode", "stp mode", "vtp mode", "vtp domain",
], key=len, reverse=True)
TOP_REPLACING = {"hostname", "sysname", "ip default-gateway", "ip domain-name", "ip domain name",
                 "spanning-tree mode", "stp mode", "vtp mode", "vtp domain"}
# On/off settings: "no shutdown" is remembered (it is a state), not just deleted.
ON_OFF = {"shutdown", "switchport", "portswitch"}

# Interface names: short form -> full form ("Gi0/1" -> "gigabitethernet0/1").
FULL_NAMES = ["ethernet", "fastethernet", "gigabitethernet", "tengigabitethernet",
              "xgigabitethernet", "serial", "loopback", "vlanif", "vlan", "port-channel",
              "tunnel", "eth-trunk", "nve"]
SHORT_NAMES = {"e": "ethernet", "et": "ethernet", "eth": "ethernet", "f": "fastethernet",
               "fa": "fastethernet", "g": "gigabitethernet", "gi": "gigabitethernet",
               "gig": "gigabitethernet", "ge": "gigabitethernet", "te": "tengigabitethernet",
               "xge": "xgigabitethernet", "s": "serial", "se": "serial", "lo": "loopback",
               "vl": "vlan", "po": "port-channel", "tu": "tunnel"}
LOGICAL = {"loopback", "vlan", "vlanif", "port-channel", "tunnel", "eth-trunk", "nve"}


def syntax_of(vendor: str | None) -> str:
    return SYNTAX.get(vendor or "", "ios")


def canonical(name: str) -> str:
    """'Gi0/1', 'gigabitethernet 0/1' -> 'gigabitethernet0/1' (so names can be compared)."""
    name = name.replace(" ", "").lower()
    match = re.match(r"([a-z-]+)([\d/.:]+)$", name)
    if not match:
        return name
    kind, number = match[1], match[2]
    if kind not in FULL_NAMES:
        kind = SHORT_NAMES.get(kind) or next((f for f in FULL_NAMES if f.startswith(kind)), kind)
    return kind + number


def is_physical(name: str) -> bool:
    """Ethernet0/0, Gi0/1 = a real port (can't be deleted). Loopback5, Vlan10 = logical.
    A subinterface (Ethernet0/1.10) is logical too: it can be deleted."""
    if "." in name:
        return False
    kind = re.match(r"[a-z-]*", canonical(name))[0]
    return kind not in LOGICAL


def vlan_list(text: str) -> list[int]:
    """'10,20-22' (Cisco) or '10 20 to 22' (Huawei) -> [10, 20, 21, 22]."""
    text = re.sub(r"\s+to\s+", "-", text.strip().lower())
    numbers = []
    for part in re.split(r"[,\s]+", text):
        if re.fullmatch(r"\d+-\d+", part):
            low, high = map(int, part.split("-"))
            numbers += range(low, min(high, low + 4094) + 1)
        elif part.isdigit():
            numbers.append(int(part))
    return numbers


def read_address(address: str, mask: str | None = None):
    """'10.0.0.1' + '255.255.255.0' (or '24', or '10.0.0.1/24') -> (ip, network).
    The network is None when no mask is known. Raises ValueError when it's not valid."""
    if mask:
        address = f"{address}/{mask}"
    if "/" in address:
        interface = ipaddress.ip_interface(address)
        return interface.ip, interface.network
    return ipaddress.ip_address(address), None


def section_keys(low: str, syntax: str) -> list[str]:
    """The section(s) a line opens, e.g. 'interface e0/1' -> ['interface ethernet0/1'],
    'vlan 10,20' -> ['vlan 10', 'vlan 20']. [] if the line is not a section."""
    if match := re.match(r"interface\s+(.+)$", low):
        return ["interface " + canonical(match[1])]
    if syntax == "vrp":
        if match := re.match(r"vlan\s+(\d+)$", low):
            return [f"vlan {match[1]}"]
        if match := re.match(r"vlan batch\s+(.+)$", low):
            return [f"vlan {v}" for v in vlan_list(match[1])]
        if match := re.match(r"acl(?: number| name)?\s+(\S+)", low):
            return [f"acl {match[1]}"]
        if re.match(r"(ospf|bgp|rip|isis)\b", low):
            return [low]
        return []
    if match := re.match(r"vlan\s+([\d,\-\s]+)$", low):
        return [f"vlan {v}" for v in vlan_list(match[1])]
    if re.match(r"(router \S+|ip access-list (standard|extended) \S+$|line (vty|con|console|aux)\b)", low):
        return [low]
    return []


def setting_key(low: str, section: str | None) -> str:
    """Which setting a line sets, so a newer line can replace it or "no ..." can remove it.
    'ip address 10.0.0.1 255.0.0.0' -> 'ip address',  'ip access-group X in' -> 'ip access-group in'."""
    words = low.split()
    if low.startswith("ip access-group") and len(words) >= 3:
        return "ip access-group " + words[-1]           # one ACL per direction
    if low.startswith("traffic-filter") and len(words) >= 2:
        return "traffic-filter " + words[1]             # Huawei: inbound / outbound
    if low.startswith("ip address") and words[-1] in ("secondary", "sub"):
        return low                                      # extra addresses add up
    for key in REPLACING:
        if low == key or low.startswith(key + " "):
            if section is None and key not in TOP_REPLACING:
                break
            return key
    if section and (section.startswith(("acl ", "ip access-list"))):
        if words[0] == "rule" and len(words) > 1:
            return "rule " + words[1]                   # Huawei ACL rule number
        if words[0].isdigit():
            return words[0]                             # Cisco numbered ACL entry
    if section and section.startswith("interface "):
        # unknown interface setting: its words before the first number ('ip ospf cost 10')
        key = []
        for word in words:
            if any(ch.isdigit() for ch in word):
                break
            key.append(word)
        return " ".join(key) or low
    return low


class Config:
    def __init__(self, syntax: str = "ios"):
        self.syntax = syntax
        self.neg = NEGATION.get(syntax, "no")
        self.sections: dict[str, dict[str, str]] = {}
        self.names: dict[str, str] = {}   # section key -> how it was written ("interface Ethernet0/0")
        self.top: dict[str, str] = {}
        self.complete = False     # True = built from a real config backup (missing = really absent)
        self.vlans_known = False  # True = the backup lists the device's VLANs
        self.overwritten = []     # [(section, old line, new line)] set twice in ONE apply()

    def copy(self) -> "Config":
        return deepcopy(self)

    def apply(self, lines) -> "Config":
        """Run config lines on the model, like the device would. Returns self."""
        context, seen = None, set()
        self.overwritten = []
        for raw in lines:
            line = " ".join(str(raw).split())
            low = line.lower()
            if not line or low in EXITS:
                context = None
                continue
            negated = low.startswith(self.neg + " ")
            body = line[len(self.neg) + 1:] if negated else line
            keys = section_keys(body.lower(), self.syntax)
            if keys:
                for key in keys:
                    if negated:
                        self.sections.pop(key, None)
                    else:
                        self.sections.setdefault(key, {})
                        self.names.setdefault(key, body)
                batch = body.lower().startswith("vlan batch")
                context = None if negated or batch else keys
            elif context and not TOP_LEVEL.match(body.lower()):
                for key in context:
                    if key in self.sections:
                        self._set(self.sections[key], body, negated, key, seen)
            else:
                context = None
                self._set(self.top, body, negated, None, seen)
        return self

    def _set(self, store, body, negated, section, seen):
        low = body.lower()
        key = setting_key(low, section)
        if negated and key in ON_OFF:
            store[key] = f"{self.neg} {body}"
        elif negated:
            for old in [k for k, v in store.items()
                        if k == key or k.startswith(key + " ") or v.lower() == low]:
                del store[old]
        else:
            old = store.get(key)
            if old and old.lower() != low and (section, key) in seen:
                self.overwritten.append((section, old, body))
            store[key] = body
            seen.add((section, key))

    # ---- questions the checks ask ----
    def items(self) -> dict:
        """Everything as one flat dict, to compare two moments: (section, setting) -> line."""
        flat = {}
        for key, settings in self.sections.items():
            flat[(key, None)] = self.names.get(key, key)
            for setting, line in settings.items():
                flat[(key, setting)] = line
        for setting, line in self.top.items():
            flat[(None, setting)] = line
        return flat

    def display(self, section: str | None) -> str:
        """How to name a section in a message: 'interface Ethernet0/0' -> 'Ethernet0/0'."""
        if section is None:
            return ""
        name = self.names.get(section, section)
        return name[len("interface "):] if name.lower().startswith("interface ") else name

    def vlans(self) -> dict[int, str | None]:
        """{10: 'Sales', 20: None}"""
        result = {}
        for key, settings in self.sections.items():
            if key.startswith("vlan ") and key[5:].isdigit():
                line = settings.get("name") or settings.get("description") or ""
                name = line.split(None, 1)[1].strip('"') if " " in line else None
                result[int(key[5:])] = name
        return result

    def interfaces(self) -> dict[str, dict[str, str]]:
        """{'ethernet0/0': {setting: line}}"""
        return {k[len("interface "):]: v for k, v in self.sections.items() if k.startswith("interface ")}

    def addresses(self, interface: str) -> list:
        """[(ip, network or None, line)] of one interface (bad addresses are skipped)."""
        result = []
        for setting, line in self.interfaces().get(interface, {}).items():
            words = line.split()
            if setting.startswith("ip address") and len(words) >= 3:
                mask = words[3] if len(words) > 3 and words[3].lower() not in ("secondary", "sub") else None
                try:
                    ip, network = read_address(words[2], mask)
                except ValueError:
                    continue
                result.append((ip, network, line))
        return result

    def mode(self, interface: str) -> str | None:
        """'access', 'trunk', 'routed' (no switchport) or None (not set / unknown)."""
        settings = self.interfaces().get(interface, {})
        if settings.get("switchport", "").lower() == f"{self.neg} switchport":
            return "routed"
        for key in ("switchport mode", "port link-type"):
            if key in settings:
                return settings[key].split()[-1].lower()
        return None

    def access_vlan(self, interface: str) -> int | None:
        settings = self.interfaces().get(interface, {})
        line = settings.get("switchport access vlan") or settings.get("port default vlan")
        return int(line.split()[-1]) if line and line.split()[-1].isdigit() else None

    def trunk_vlans(self, interface: str) -> list[int] | None:
        """VLANs allowed on a trunk ([] = none set, None = 'all')."""
        settings = self.interfaces().get(interface, {})
        line = settings.get("switchport trunk allowed vlan") or settings.get("port trunk allow-pass vlan")
        if not line:
            return []
        text = re.sub(r"^.*?\bvlan\s+(add\s+)?", "", line.lower())
        return None if "all" in text else vlan_list(text)

    def acls(self) -> set[str]:
        """Names / numbers of the access lists defined on the device."""
        names = set()
        for key in self.sections:
            if key.startswith("ip access-list") or key.startswith("acl "):
                names.add(key.split()[-1])
        for setting in self.top:
            if setting.startswith("access-list "):
                names.add(setting.split()[1])
        return names

    def acls_used(self, interface: str) -> list[str]:
        settings = self.interfaces().get(interface, {})
        used = []
        for setting, line in settings.items():
            words = line.split()
            if setting.startswith("ip access-group") and len(words) >= 3:
                used.append(words[2])
            elif setting.startswith("traffic-filter") and words:
                used.append(words[-1])
        return used

    def routes(self) -> list:
        """[(network, next hop, line)] of the static routes."""
        result = []
        for line in self.top.values():
            words = line.split()
            if line.lower().startswith(("ip route ", "ip route-static ")) and len(words) >= 5:
                try:
                    network = ipaddress.ip_network(f"{words[2]}/{words[3]}", strict=False)
                    result.append((network, ipaddress.ip_address(words[4]), line))
                except ValueError:
                    continue
        return result

    def ospf_networks(self) -> list:
        """[(network, line)] from 'network 10.0.0.0 0.0.0.255 area 0' lines."""
        result = []
        for key, settings in self.sections.items():
            if not (key.startswith("router ospf") or key.startswith("ospf")):
                continue
            for line in settings.values():
                words = line.split()
                if words[0].lower() == "network" and len(words) >= 3:
                    try:
                        result.append((ipaddress.ip_network(f"{words[1]}/{words[2]}", strict=False), line))
                    except ValueError:
                        continue
        return result
