"""Find out what is on the network, the simplest way possible.

1. scan_subnet: ping every address in a subnet -> who is alive?
2. check which management ports are open (22 SSH, 23 Telnet, 80 web)
3. discover_links: ask devices who their neighbors are (Cisco CDP)
   and which IP addresses their interfaces have

Ideas for later: SNMP, LLDP, reading ARP/MAC tables, traceroute.
"""
import ipaddress
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..vendors import get_vendor
from .drivers import DRIVERS, get_driver

PORTS = {22: "ssh", 23: "telnet", 80: "http"}


def ping(ip: str) -> bool:
    """True if the device answers. We send 2 pings: right after a device comes back,
    the router in between often drops the FIRST packet while it looks up the MAC
    address (ARP), so one lost ping doesn't mean "down"."""
    if platform.system() == "Windows":
        command = ["ping", "-n", "2", "-w", "1000", ip]
    else:
        command = ["ping", "-c", "2", "-W", "1", ip]
    result = subprocess.run(command, capture_output=True, text=True, errors="ignore")
    # A real answer contains "TTL=". (Windows ping can "succeed" on a
    # "Destination host unreachable" message, which is not an answer from the device.)
    return result.returncode == 0 and "ttl=" in result.stdout.lower()


def open_ports(ip: str) -> list[str]:
    found = []
    for port, name in PORTS.items():
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((ip, port)) == 0:
                found.append(name)
    return found


def scan_subnet(cidr: str) -> list[str]:
    hosts = [str(ip) for ip in ipaddress.ip_network(cidr, strict=False).hosts()]
    if len(hosts) > 1024:
        raise ValueError("Subnet too big, use /22 or smaller")
    with ThreadPoolExecutor(max_workers=64) as pool:  # ping many hosts at the same time
        alive = pool.map(ping, hosts)
    return [ip for ip, up in zip(hosts, alive) if up]


def discover(kb, cidr: str) -> list[dict]:
    """Ping-scan the subnet and add new devices to the knowledge base."""
    found = []
    for ip in scan_subnet(cidr):
        ports = open_ports(ip)
        device = kb.find_by_ip(ip)
        if device:
            kb.update_device(device["name"], state="up", ports=ports)
        else:
            # We don't know the vendor yet: the user sets it in the web page.
            device = {"name": f"host-{ip}", "ip": ip, "vendor": "unknown",
                      "protocol": "ssh" if "ssh" in ports else "telnet" if "telnet" in ports else "",
                      "ports": ports, "state": "up"}
            kb.add_device(device)
        found.append(device)
    return found


def refresh_states(kb) -> None:
    """Ping every known device and save up/down in the knowledge base."""
    devices = [d for d in kb.list_devices() if d.get("ip")]
    with ThreadPoolExecutor(max_workers=64) as pool:
        results = pool.map(lambda d: ping(d["ip"]), devices)
    for device, up in zip(devices, results):
        kb.update_device(device["name"], state="up" if up else "down")


def discover_links(kb) -> list[str]:
    """Log in to each device, save its interface IPs and ask for its neighbors.
    Old links that no longer exist are removed (see _remove_stale_links).
    Returns any errors."""
    names = {d["name"] for d in kb.list_devices()}
    errors = []
    asked = set()   # devices we really asked for neighbors (logged in + vendor supports it)
    found = set()   # links seen now, e.g. {"R1", "SW"}
    for device in kb.list_devices():
        if device.get("vendor") not in DRIVERS:
            continue  # e.g. "unknown" devices found by the ping scan: we can't log in
        try:
            with get_driver(device) as driver:
                kb.update_device(device["name"], interfaces=driver.get_interfaces())
                for neighbor in driver.get_neighbors():
                    if neighbor in names:
                        kb.add_link(device["name"], neighbor)
                        found.add(frozenset((device["name"], neighbor)))
            profile = get_vendor(device.get("vendor"))
            if profile and profile.neighbors:
                asked.add(device["name"])
        except Exception as e:  # unknown vendor, unreachable, wrong password...
            errors.append(f"{device['name']}: {e}")
    _remove_stale_links(kb, asked, found)
    return errors


def _remove_stale_links(kb, asked, found):
    """Remove a link only when we are SURE it's gone: both devices answered the neighbor
    question and neither reported the other. Links added by hand are never removed,
    and nothing is removed for devices we couldn't log in to."""
    for link in kb.list_links():
        both_asked = link["a"] in asked and link["b"] in asked
        if both_asked and not link.get("manual") and frozenset((link["a"], link["b"])) not in found:
            kb.delete_link(link["a"], link["b"])
