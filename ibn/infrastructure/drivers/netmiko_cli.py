"""Traditional CLI devices over SSH or Telnet, using the Netmiko library.

Netmiko already knows 100+ vendors. Everything vendor-specific (Netmiko type, which
command shows the config, how errors look...) comes from the vendor profile in
ibn/vendors/, so this file never changes when a vendor is added.
Netmiko's vendor list: https://github.com/ktbyers/netmiko/blob/develop/PLATFORMS.md
"""
from netmiko import ConnectHandler

from ... import settings
from ...vendors import get_vendor
from .base import Driver


class NetmikoDriver(Driver):
    def connect(self):
        self.profile = get_vendor(self.device["vendor"])
        device_type = self.profile.netmiko_type
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
        return self.conn.send_command(self.profile.show_config)

    def send_config(self, commands):
        output = self.conn.send_config_set(commands)  # enters/leaves config mode for us
        for marker in self.profile.error_markers:
            if marker in output:
                raise RuntimeError(f"Device rejected a command:\n{output}")
        return output

    def run_commands(self, commands):
        output = []
        for command in commands:
            # read_timeout: a ping to an unreachable address can take ~10-20 seconds
            result = self.conn.send_command(command, read_timeout=60)
            output.append(f"{self.device['name']}# {command}\n{result}")
        return "\n\n".join(output)

    def get_interfaces(self):
        if not self.profile.show_interfaces:
            return []
        output = self.conn.send_command(self.profile.show_interfaces)
        return self.profile.parse_interfaces(output)  # -> ["Ethernet0/0 10.1.2.1", ...]

    def get_neighbors(self):
        # Cisco Discovery Protocol tells us who is plugged into this device.
        if self.profile.neighbors != "cdp":
            return []
        rows = self.conn.send_command("show cdp neighbors detail", use_textfsm=True)
        if not isinstance(rows, list):  # parsing failed -> no neighbors
            return []
        names = [r.get("neighbor_name") or r.get("destination_host") or "" for r in rows]
        return [n.split(".")[0] for n in names if n]  # "SW1.lab.local" -> "SW1"
