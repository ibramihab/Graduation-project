"""Safety rules, per vendor. Each rule is a regular expression + the reason.

To support a new vendor, add its own list here. Vendors without a list use "default".
"""

BLOCKED = {
    "default": [
        (r"^(reload|reboot|shutdown system)", "restarts the device"),
        (r"^(erase|format|delete|write erase)", "deletes files or the whole config"),
    ],
    "cisco_ios": [
        (r"^reload", "restarts the device"),
        (r"^(erase|format|delete|write erase)", "deletes files or the whole config"),
        (r"^no username", "can lock us out of the device"),
        (r"^no (ip )?ssh|^line vty .*\btransport input none", "can cut our SSH access"),
        (r"^crypto key zeroize", "deletes the SSH keys"),
        (r"^no aaa new-model", "changes how logins work"),
        (r"^enable secret|^enable password", "changes the enable password"),
    ],
}
BLOCKED["cisco_nxos"] = BLOCKED["cisco_ios"]
# web_gui steps are English sentences, not CLI
BLOCKED["web_gui"] = [
    (r"factory|reset to default|restore default|default settings", "erases all the router's settings"),
    (r"(admin|login|management|web) password|username", "can lock us out of the router"),
]

# Not blocked, but the user should look twice before approving.
WARN = [
    (r"^shutdown$", "turns an interface off"),
    (r"^no ip address", "removes an IP address (could be the management IP)"),
    (r"^no (vlan|interface|router)", "removes something that may be in use"),
    (r"access-list|access-group", "a firewall rule can block traffic, including ours"),
    (r"\b(reboot|restart)\b", "the router will be offline for a minute or two"),
    (r"wi-?fi|wlan|ssid|wireless", "Wi-Fi users (maybe you) can be disconnected"),
]

# Commands allowed in a "check" step (read-only, exec mode). Anything else is refused,
# so a "check" can never change the device.
CHECK_ALLOWED = r"^(ping|traceroute|show|display)\b"
CHECK_ALLOWED_WEB = r"^(read|show|check|get|find|look|list|what)\b"  # web_gui: English
