"""A FAKE device that lives in memory. Use vendor "simulated" to try the whole
system without any real router. Any command containing the word "invalid"
fails, so you can see the rollback working."""
from .base import Driver

# device name -> list of config lines it has "applied"
FAKE_CONFIGS: dict[str, list[str]] = {}


class SimulatedDriver(Driver):
    def connect(self):
        FAKE_CONFIGS.setdefault(self.device["name"], [f"hostname {self.device['name']}"])

    def disconnect(self):
        pass

    def get_config(self):
        return "\n".join(FAKE_CONFIGS[self.device["name"]])

    def send_config(self, commands):
        for command in commands:
            if "invalid" in command.lower():
                raise RuntimeError(f"% Invalid input detected: {command}")
            FAKE_CONFIGS[self.device["name"]].append(command)
        return "\n".join(f"{self.device['name']}(config)# {c}" for c in commands)
