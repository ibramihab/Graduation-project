# Static and default routes (Cisco IOS)
Syntax: ip route <destination network> <subnet mask> <next-hop IP | exit interface> [distance]
- Example: ip route 10.70.0.0 255.255.0.0 10.0.12.2
- Default route: ip route 0.0.0.0 0.0.0.0 <next-hop>
- Backup (floating) route: add a distance bigger than the main route, e.g. 200.
- Host route: mask 255.255.255.255.
- Undo: the same line with "no " in front, copied exactly (with the distance or interface if used).
Rules:
- The destination is the NETWORK address (10.70.0.0, not 10.70.0.5) and the mask is a subnet mask.
- The next hop must be the neighbor's IP on a directly connected link (in the same subnet as one of this router's interfaces).
- For two LANs to talk, BOTH directions need a route (each router must know the way back).
- A static route (distance 1) wins over OSPF (110) for the same network.
Check: show ip route, show ip route static, show ip route <address>, ping, traceroute.
