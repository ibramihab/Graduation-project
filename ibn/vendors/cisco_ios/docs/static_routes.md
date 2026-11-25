# Static and default routes (Cisco IOS)

## Static route to a network
Syntax: ip route <destination network> <subnet mask> <next-hop IP | exit interface> [distance]
- The destination is the NETWORK address (10.70.0.0, not 10.70.0.5) and the mask is a subnet mask.
- The next hop must be the neighbor's IP on a directly connected link (in the same subnet as one of this router's interfaces).
- Undo: the same line with "no " in front, copied exactly.

Example: on R1 add a static route to 192.168.2.0/24 via R2
    Plan: Static route on R1 to 192.168.2.0/24 through R2 (10.0.12.2)
    R1 config:
        ip route 192.168.2.0 255.255.255.0 10.0.12.2
    R1 undo:
        no ip route 192.168.2.0 255.255.255.0 10.0.12.2

Example: make HQ reach the 172.16.30.0/24 network through BR1
    Plan: Static route on HQ to 172.16.30.0/24 through BR1 (10.10.1.2, BR1's address on the HQ-BR1 link)
    HQ config:
        ip route 172.16.30.0 255.255.255.0 10.10.1.2
    HQ undo:
        no ip route 172.16.30.0 255.255.255.0 10.10.1.2

Example: ضيف راوت ستاتيك على R2 لشبكة 192.168.1.0/24 عن طريق R1
    Plan: Static route on R2 to 192.168.1.0/24 through R1 (10.0.12.1)
    R2 config:
        ip route 192.168.1.0 255.255.255.0 10.0.12.1
    R2 undo:
        no ip route 192.168.1.0 255.255.255.0 10.0.12.1

## Several routes, or a route out of an interface
- One "ip route" line per destination network.
- Instead of a next-hop IP you can name the exit interface (ip route <net> <mask> Ethernet0/1).

Example: send traffic for 10.70.0.0/16 out of R5's interface e0/1
    Plan: Static route on R5 to 10.70.0.0/16 out of Ethernet0/1 (exit interface instead of a next-hop IP)
    R5 config:
        ip route 10.70.0.0 255.255.0.0 Ethernet0/1
    R5 undo:
        no ip route 10.70.0.0 255.255.0.0 Ethernet0/1

Example: on EDGE add routes to the branch networks 10.81.0.0/24 and 10.82.0.0/24 via 10.99.0.2
    Plan: Two static routes on EDGE, both through 10.99.0.2
    EDGE config:
        ip route 10.81.0.0 255.255.255.0 10.99.0.2
        ip route 10.82.0.0 255.255.255.0 10.99.0.2
    EDGE undo:
        no ip route 10.81.0.0 255.255.255.0 10.99.0.2
        no ip route 10.82.0.0 255.255.255.0 10.99.0.2

Example: BR2 can't reach the head office 10.10.0.0/16, add the missing route through HQ
    Plan: Static route on BR2 to 10.10.0.0/16 through HQ (10.20.1.1, HQ's address on the BR2-HQ link)
    BR2 config:
        ip route 10.10.0.0 255.255.0.0 10.20.1.1
    BR2 undo:
        no ip route 10.10.0.0 255.255.0.0 10.20.1.1

## Default route
Syntax: ip route 0.0.0.0 0.0.0.0 <next-hop>
- Used for "everything else", e.g. towards the internet or the main router.
- A static route (distance 1) wins over OSPF (110) for the same network.

Example: add a default route on R3 towards R2
    Plan: Default route on R3: everything unknown goes to R2 (10.0.23.2)
    R3 config:
        ip route 0.0.0.0 0.0.0.0 10.0.23.2
    R3 undo:
        no ip route 0.0.0.0 0.0.0.0 10.0.23.2

## Routes in both directions
- For two LANs to talk, BOTH directions need a route: each router must know the way back.

Example: let the 192.168.10.0/24 LAN behind R1 and the 192.168.20.0/24 LAN behind R2 reach each other with static routes
    Plan: Static routes in both directions over the R1-R2 link (10.0.12.0/24): each router learns the other LAN
    R1 config:
        ip route 192.168.20.0 255.255.255.0 10.0.12.2
    R1 undo:
        no ip route 192.168.20.0 255.255.255.0 10.0.12.2
    R2 config:
        ip route 192.168.10.0 255.255.255.0 10.0.12.1
    R2 undo:
        no ip route 192.168.10.0 255.255.255.0 10.0.12.1

## Backup (floating) route and host route
- Backup route: add a distance bigger than the main route, e.g. 200. It is used only if the main route disappears.
- Host route (one address): mask 255.255.255.255.

Example: add a backup route on R1 to 10.50.0.0/16 via R3 that is used only if the main path fails
    Plan: Floating static route on R1 (administrative distance 200) to 10.50.0.0/16 through R3 (10.0.13.3)
    R1 config:
        ip route 10.50.0.0 255.255.0.0 10.0.13.3 200
    R1 undo:
        no ip route 10.50.0.0 255.255.0.0 10.0.13.3 200

Example: route traffic for the server 172.20.5.10 from R2 through R4
    Plan: Host route (/32) on R2 to the server 172.20.5.10 through R4 (10.0.24.4)
    R2 config:
        ip route 172.20.5.10 255.255.255.255 10.0.24.4
    R2 undo:
        no ip route 172.20.5.10 255.255.255.255 10.0.24.4

## Remove a static route
- The same line with "no " in front, copied exactly (with the distance or interface if used).

Example: remove the static route to 192.168.2.0/24 from R1
    Plan: Delete R1's static route to 192.168.2.0/24 (the rollback adds it back)
    R1 config:
        no ip route 192.168.2.0 255.255.255.0 10.0.12.2
    R1 undo:
        ip route 192.168.2.0 255.255.255.0 10.0.12.2

## Check routes
Check: show ip route, show ip route static, show ip route <address>, ping, traceroute.
