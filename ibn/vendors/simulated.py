"""A fake device for practice and tests. It behaves like Cisco IOS (same rules)."""
from dataclasses import replace

from .cisco_ios import PROFILE as IOS

PROFILE = replace(
    IOS,
    name="simulated",
    description="Simulated device (use Cisco IOS commands)",
    netmiko_type="",  # not reached over SSH: it has its own fake driver
    neighbors="",
)
