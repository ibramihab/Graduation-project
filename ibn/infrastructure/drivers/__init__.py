"""Driver registry: device "vendor" -> the class that knows how to talk to it.

To support a new vendor or method, write a Driver class and add ONE line here.
Ideas for later:
    "juniper_junos": JunosDriver      (CLI with commit)
    "rest_api":      RestApiDriver    (devices with an HTTP/RESTCONF API)
    "netconf":       NetconfDriver    (ncclient library)
    "sdn_onos":      OnosDriver       (talks to an SDN controller instead of a device)
"""
from .base import Driver
from .netmiko_cli import NETMIKO_TYPES, NetmikoDriver
from .simulated import SimulatedDriver
from .web_gui import WebGuiDriver

DRIVERS: dict[str, type[Driver]] = {
    **{vendor: NetmikoDriver for vendor in NETMIKO_TYPES},  # cisco_ios, arista_eos, ...
    "web_gui": WebGuiDriver,
    "simulated": SimulatedDriver,
}


def get_driver(device: dict) -> Driver:
    vendor = device.get("vendor")
    if vendor not in DRIVERS:
        raise ValueError(f"No driver for vendor '{vendor}'. Supported: {sorted(DRIVERS)}")
    return DRIVERS[vendor](device)
