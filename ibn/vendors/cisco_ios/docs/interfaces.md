# Interfaces (Cisco IOS)
- Always: "interface <name>" first, then its settings on the next lines.
- Use the real names of the device (IOL: Ethernet0/0, Ethernet0/1 ... not GigabitEthernet).
- IP address: ip address 10.0.25.1 255.255.255.0 (a subnet mask, not /24), then no shutdown.
  Undo: no ip address (or put back the old address) + shutdown.
- Extra address: ip address <ip> <mask> secondary.
- Turn off / on: shutdown / no shutdown. Label: description <text> (undo: no description).
- Loopback: interface Loopback1 + ip address 1.1.1.1 255.255.255.255. Undo: no interface Loopback1.
- An interface can't get the network address (.0 for /24) or the broadcast address (.255 for /24).
- Two interfaces of the same router can't be in the same subnet.
Check: show ip interface brief, show interfaces <name>, show running-config interface <name>.
