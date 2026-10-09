"""Find out what is on the network, the simplest way possible.

1. scan_subnet: ping every address in a subnet -> who is alive?
2. check which management ports are open (22 SSH, 23 Telnet, 80 web)
3. discover_links: ask devices who their neighbors are (Cisco CDP)

Ideas for later: SNMP, LLDP, reading ARP/MAC tables, traceroute.
"""
import ipaddress
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .drivers import DRIVERS, get_driver

PORTS = {22: "ssh", 23: "telnet", 80: "http"}


def ping(ip: str) -> bool:
    if platform.system() == "Windows":
        command = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        command = ["ping", "-c", "1", "-W", "1", ip]
    return subprocess.run(command, capture_output=True).returncode == 0


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
    """Log in to each device and ask for its neighbors. Returns any errors."""
    names = {d["name"] for d in kb.list_devices()}
    errors = []
    for device in kb.list_devices():
        if device.get("vendor") not in DRIVERS:
            continue  # e.g. "unknown" devices found by the ping scan: we can't log in
        try:
            with get_driver(device) as driver:
                for neighbor in driver.get_neighbors():
                    if neighbor in names:
                        kb.add_link(device["name"], neighbor)
        except Exception as e:  # unknown vendor, unreachable, wrong password...
            errors.append(f"{device['name']}: {e}")
    return errors
