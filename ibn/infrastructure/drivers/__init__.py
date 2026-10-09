"""Driver registry: device "vendor" -> the class that knows how to talk to it.

Every vendor profile with a Netmiko type (ibn/vendors/) gets the NetmikoDriver
automatically, so a new CLI vendor needs no change here.
A new METHOD (API, NETCONF, SDN...) = write a Driver class and add ONE line here.
Ideas for later:
    "juniper_junos": JunosDriver      (CLI with commit)
    "rest_api":      RestApiDriver    (devices with an HTTP/RESTCONF API)
    "netconf":       NetconfDriver    (ncclient library)
    "sdn_onos":      OnosDriver       (talks to an SDN controller instead of a device)
"""
from .base import Driver
from ...vendors import VENDORS
from .netmiko_cli import NetmikoDriver
from .simulated import SimulatedDriver

DRIVERS: dict[str, type[Driver]] = {
    **{name: NetmikoDriver for name, p in VENDORS.items() if p.netmiko_type},  # cisco_ios, huawei, ...
    "simulated": SimulatedDriver,
}


def get_driver(device: dict) -> Driver:
    vendor = device.get("vendor")
    if vendor not in DRIVERS:
        raise ValueError(f"No driver for vendor '{vendor}'. Supported: {sorted(DRIVERS)}")
    return DRIVERS[vendor](device)
