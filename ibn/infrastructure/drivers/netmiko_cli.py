"""Traditional CLI devices over SSH or Telnet, using the Netmiko library.

Netmiko already knows 100+ vendors, so supporting a new CLI vendor is
usually ONE line in NETMIKO_TYPES below (plus one line in drivers/__init__.py).
Full list: https://github.com/ktbyers/netmiko/blob/develop/PLATFORMS.md
"""
from netmiko import ConnectHandler

from ... import settings
from .base import Driver

# our vendor name -> (netmiko device type, command that shows the config)
NETMIKO_TYPES = {
    "cisco_ios": ("cisco_ios", "show running-config"),
    "cisco_nxos": ("cisco_nxos", "show running-config"),
    "arista_eos": ("arista_eos", "show running-config"),
    "huawei": ("huawei", "display current-configuration"),
    "mikrotik_routeros": ("mikrotik_routeros", "/export"),
}

# Text that means the device did not accept a command.
ERROR_MARKERS = ["% Invalid", "% Incomplete", "% Ambiguous", "% Unknown", "Error:"]


class NetmikoDriver(Driver):
    def connect(self):
        device_type, self.show_config_cmd = NETMIKO_TYPES[self.device["vendor"]]
        if self.device.get("protocol") == "telnet":
            device_type += "_telnet"
        self.conn = ConnectHandler(
            device_type=device_type,
            host=self.device["ip"],
            username=self.device.get("username") or settings.DEVICE_USERNAME,
            password=self.device.get("password") or settings.DEVICE_PASSWORD,
            secret=settings.DEVICE_SECRET,
        )
        if settings.DEVICE_SECRET:
            self.conn.enable()

    def disconnect(self):
        if getattr(self, "conn", None):
            self.conn.disconnect()

    def get_config(self):
        return self.conn.send_command(self.show_config_cmd)

    def send_config(self, commands):
        output = self.conn.send_config_set(commands)  # enters/leaves config mode for us
        for marker in ERROR_MARKERS:
            if marker in output:
                raise RuntimeError(f"Device rejected a command:\n{output}")
        return output

    def get_neighbors(self):
        # Cisco Discovery Protocol tells us who is plugged into this device.
        if not self.device["vendor"].startswith("cisco"):
            return []
        rows = self.conn.send_command("show cdp neighbors detail", use_textfsm=True)
        if not isinstance(rows, list):  # parsing failed -> no neighbors
            return []
        names = [r.get("neighbor_name") or r.get("destination_host") or "" for r in rows]
        return [n.split(".")[0] for n in names if n]  # "SW1.lab.local" -> "SW1"
