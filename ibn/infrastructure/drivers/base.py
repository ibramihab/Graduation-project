"""The Driver contract: how the control layer talks to ANY device.

Every vendor / access method (SSH, Telnet, web GUI, REST API, and later SDN
controllers) is one class with these methods. The control layer never needs
to know which one it is using.
"""
from abc import ABC, abstractmethod


class Driver(ABC):
    def __init__(self, device: dict):
        self.device = device  # the device dict from the knowledge base

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_config(self) -> str:
        """Return the current configuration (used as a backup before changes)."""

    @abstractmethod
    def send_config(self, commands: list[str]) -> str:
        """Apply the commands. Raise an exception if the device reports an error."""

    def run_commands(self, commands: list[str]) -> str:
        """Run read-only commands (ping, show...) in normal/exec mode, return the output.
        Optional: drivers that can't do this raise an error."""
        raise NotImplementedError(f"{type(self).__name__} can't run check commands")

    def get_interfaces(self) -> list[str]:
        """Interfaces and their IP, e.g. ["Ethernet0/0 10.1.2.1", "Ethernet0/1 unassigned"]
        (so the AI knows the real names and IPs).
        Optional: drivers that can't do this just return nothing."""
        return []

    def get_neighbors(self) -> list[str]:
        """Names of directly connected devices (for topology discovery).
        Optional: drivers that can't do this just return nothing."""
        return []

    # Lets us write:  with get_driver(device) as d: ...
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
