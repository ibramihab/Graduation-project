# OSPF (Cisco IOS)
Enable and advertise networks:
- router ospf 1
- network <network> <WILDCARD mask> area 0   e.g. network 10.0.12.0 0.0.0.255 area 0
- Undo one network: router ospf 1 + no network ... area 0. Undo everything: no router ospf 1.
Or per interface: interface Ethernet0/1 + ip ospf 1 area 0 (undo: no ip ospf 1 area 0).
Rules:
- "network" uses a WILDCARD mask (0.0.0.255 for /24, 0.0.0.3 for /30, 0.0.0.0 for one address), NOT 255.255.255.0.
- Both routers of a link must advertise that link's network in the SAME area, or they never become neighbors.
- Timers (ip ospf hello-interval / dead-interval) and authentication must be the same on both ends of a link.
- passive-interface <port>: still advertises the network but sends no hellos (use towards PCs).
- default-information originate: gives the router's default route to all OSPF routers.
- ip ospf cost <n> on an interface: lower cost = preferred path.
Check: show ip ospf neighbor (FULL = OK), show ip ospf interface brief, show ip route ospf.
