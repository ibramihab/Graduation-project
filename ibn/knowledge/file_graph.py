"""A tiny graph stored in one JSON file.

No database needed, so it's perfect for learning and for tests.
The JSON looks like:
    {"devices": {"R1": {...}}, "links": [["R1", "SW1"]], "changes": {"R1": [...]}}
"""
import json
import os
import threading

from .base import KnowledgeBase


class FileGraph(KnowledgeBase):
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()  # the web server can call us from many threads
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)
        else:
            self.data = {"devices": {}, "links": [], "changes": {}}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    # ---- devices ----
    def add_device(self, device):
        with self.lock:
            existing = self.data["devices"].get(device["name"], {})
            self.data["devices"][device["name"]] = {**existing, **device}
            self._save()

    def get_device(self, name):
        device = self.data["devices"].get(name)
        return dict(device) if device else None

    def list_devices(self):
        return [dict(d) for d in self.data["devices"].values()]

    def update_device(self, name, **fields):
        with self.lock:
            if name in self.data["devices"]:
                self.data["devices"][name].update(fields)
                self._save()

    def delete_device(self, name):
        with self.lock:
            self.data["devices"].pop(name, None)
            self.data["links"] = [l for l in self.data["links"] if name not in l]
            self._save()

    # ---- links ----
    def add_link(self, a, b):
        with self.lock:
            if [a, b] not in self.data["links"] and [b, a] not in self.data["links"]:
                self.data["links"].append([a, b])
                self._save()

    def list_links(self):
        return [{"a": a, "b": b} for a, b in self.data["links"]]

    # ---- history ----
    def record_change(self, device_name, change):
        with self.lock:
            self.data["changes"].setdefault(device_name, []).append(change)
            self._save()

    def get_history(self, device_name):
        return list(self.data["changes"].get(device_name, []))
