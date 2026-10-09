"""Vendor profiles: one file per vendor with everything specific to it.

To add a vendor: create its file (copy a similar one) and add it to the list below.
The order of the list is the order of the vendor drop-down on the web page.
"""
from . import arista_eos, cisco_ios, cisco_nxos, fortigate, huawei, mikrotik_routeros, simulated
from .base import VendorProfile

VENDORS: dict[str, VendorProfile] = {p.name: p for p in (
    cisco_ios.PROFILE,
    cisco_nxos.PROFILE,
    huawei.PROFILE,
    fortigate.PROFILE,
    arista_eos.PROFILE,
    mikrotik_routeros.PROFILE,
    simulated.PROFILE,
)}


def get_vendor(name: str | None) -> VendorProfile | None:
    """The profile of a vendor, or None if we don't know it (e.g. "unknown")."""
    return VENDORS.get(name or "")
