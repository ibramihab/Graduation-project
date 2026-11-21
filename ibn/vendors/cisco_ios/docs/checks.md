# Read-only check commands (Cisco IOS) - type "check", rollback []
Reachability: ping <ip>, ping <ip> source <my interface ip>, ping <ip> repeat 100, traceroute <ip>.
- "Can network A reach B?": ping from A's gateway router WITH source = A's gateway address.
Routing: show ip route, show ip route <address>, show ip protocols, show ip ospf neighbor.
Interfaces: show ip interface brief, show interfaces <name>, show interfaces status.
Switching: show vlan brief, show interfaces trunk, show mac address-table, show spanning-tree.
Neighbors: show cdp neighbors (which device is on which port).
Config: show running-config | section <word>, show running-config interface <name>.
Services: show access-lists, show ip nat translations, show ip dhcp binding, show standby brief.
Rules: check commands start with show, ping or traceroute; never put them in a "config" step,
and never put configuration in a "check" step.
