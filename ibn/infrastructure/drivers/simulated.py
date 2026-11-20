"""A FAKE device that lives in memory. Use vendor "simulated" to try the whole
system without any real router. Any command containing the word "invalid"
fails, so you can see the rollback working. A ping answers, except a ping to
192.0.2.x (an address range reserved for examples): it gets no reply, so you can see
a failed post-validation ("verify") and its rollback."""
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

    def run_commands(self, commands):
        return "\n".join(f"{self.device['name']}# {c}\n{_fake_output(c)}" for c in commands)


def _fake_output(command: str) -> str:
    if command.lower().startswith("ping"):
        if "192.0.2." in command:
            return "Success rate is 0 percent (0/5)"
        return "!!!!!\nSuccess rate is 100 percent (5/5)"
    return "(simulated output)"
