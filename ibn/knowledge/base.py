"""The Knowledge Base contract.

The knowledge base is the system's memory of the network, stored as a GRAPH:

    (Device)-[:CONNECTED_TO]-(Device)      <- topology
    (Device)-[:HAS_CHANGE]->(Change)       <- history of what we did
    Device properties                      <- state (up/down) and last config backup

Every layer talks to the knowledge base ONLY through the methods below,
so we can swap the storage (JSON file, Neo4j, ...) without touching any layer.

A device is a plain dict, for example:
    {"name": "R1", "ip": "192.168.1.1", "vendor": "cisco_ios",
     "protocol": "ssh", "state": "up"}
"""
from abc import ABC, abstractmethod


class KnowledgeBase(ABC):
    # ---- devices (graph nodes) ----
    @abstractmethod
    def add_device(self, device: dict) -> None:
        """Create the device, or update it if a device with that name exists."""

    @abstractmethod
    def get_device(self, name: str) -> dict | None: ...

    @abstractmethod
    def list_devices(self) -> list[dict]: ...

    @abstractmethod
    def update_device(self, name: str, **fields) -> None: ...

    @abstractmethod
    def delete_device(self, name: str) -> None: ...

    # ---- links (graph edges) ----
    @abstractmethod
    def add_link(self, a: str, b: str) -> None: ...

    @abstractmethod
    def list_links(self) -> list[dict]:
        """Return [{"a": "R1", "b": "SW1"}, ...]"""

    # ---- history ----
    @abstractmethod
    def record_change(self, device_name: str, change: dict) -> None: ...

    @abstractmethod
    def get_history(self, device_name: str) -> list[dict]: ...

    # ---- helpers shared by every backend ----
    def find_by_ip(self, ip: str) -> dict | None:
        return next((d for d in self.list_devices() if d.get("ip") == ip), None)

    def save_backup(self, device_name: str, config_text: str) -> None:
        self.update_device(device_name, last_config=config_text)
