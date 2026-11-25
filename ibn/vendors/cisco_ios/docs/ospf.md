# OSPF (Cisco IOS)

## Turn on OSPF and advertise networks
- router ospf 1, then: network <network> <WILDCARD mask> area 0   e.g. network 10.0.12.0 0.0.0.255 area 0
- "network" uses a WILDCARD mask (0.0.0.255 for /24, 0.0.0.3 for /30, 0.0.0.0 for one address), NOT 255.255.255.0.
- Both routers of a link must advertise that link's network in the SAME area, or they never become neighbors.
- Undo everything: no router ospf 1.

Example: advertise the 192.168.1.0/24 network in ospf area 0 on R1
    Plan: Add 192.168.1.0/24 to OSPF process 1, area 0, on R1 (wildcard mask 0.0.0.255)
    R1 config:
        router ospf 1
        network 192.168.1.0 0.0.0.255 area 0
    R1 undo:
        router ospf 1
        no network 192.168.1.0 0.0.0.255 area 0

Example: run ospf between R1 and R2 on their shared link 10.0.12.0/24
    Plan: OSPF process 1, area 0, on both ends of the R1-R2 link (wildcard 0.0.0.255)
    R1 config:
        router ospf 1
        network 10.0.12.0 0.0.0.255 area 0
    R1 undo:
        router ospf 1
        no network 10.0.12.0 0.0.0.255 area 0
    R2 config:
        router ospf 1
        network 10.0.12.0 0.0.0.255 area 0
    R2 undo:
        router ospf 1
        no network 10.0.12.0 0.0.0.255 area 0

Example: شغل OSPF على R6 لشبكة 10.0.67.0/24
    Plan: Add 10.0.67.0/24 to OSPF process 1, area 0, on R6
    R6 config:
        router ospf 1
        network 10.0.67.0 0.0.0.255 area 0
    R6 undo:
        router ospf 1
        no network 10.0.67.0 0.0.0.255 area 0

## Advertise more networks or a loopback
- Add one "network" line per network under router ospf 1.

Example: run ospf area 0 on R5 for its networks 10.0.56.0/24 and 192.168.50.0/24
    Plan: OSPF process 1, area 0, on R5 for both of its networks (wildcard 0.0.0.255)
    R5 config:
        router ospf 1
        network 10.0.56.0 0.0.0.255 area 0
        network 192.168.50.0 0.0.0.255 area 0
    R5 undo:
        router ospf 1
        no network 10.0.56.0 0.0.0.255 area 0
        no network 192.168.50.0 0.0.0.255 area 0

Example: advertise loopback 0 of R3 (3.3.3.3/32) in ospf
    Plan: Add R3's loopback 3.3.3.3/32 to OSPF area 0 (a /32 uses wildcard 0.0.0.0)
    R3 config:
        router ospf 1
        network 3.3.3.3 0.0.0.0 area 0
    R3 undo:
        router ospf 1
        no network 3.3.3.3 0.0.0.0 area 0

## OSPF on one interface
- interface Ethernet0/1 + ip ospf 1 area 0 (undo: no ip ospf 1 area 0).

Example: enable ospf directly on interface e0/2 of R6
    Plan: Put R6 Ethernet0/2 in OSPF process 1, area 0, with the interface command
    R6 config:
        interface Ethernet0/2
        ip ospf 1 area 0
    R6 undo:
        interface Ethernet0/2
        no ip ospf 1 area 0

## Passive interface
- passive-interface <port>: still advertises the network but sends no hellos (use towards PCs).

Example: stop ospf hellos towards the users on R1 e0/2 but keep advertising that network
    Plan: Make Ethernet0/2 a passive OSPF interface on R1 (the network is still advertised)
    R1 config:
        router ospf 1
        passive-interface Ethernet0/2
    R1 undo:
        router ospf 1
        no passive-interface Ethernet0/2

## Cost and timers
- ip ospf cost <n> on an interface: lower cost = preferred path.
- Timers (ip ospf hello-interval / dead-interval) and authentication must be the same on both ends of a link.

Example: make R2 prefer the link on e0/1 by setting ospf cost 10 there
    Plan: OSPF cost 10 on R2 Ethernet0/1 (lower cost = preferred path)
    R2 config:
        interface Ethernet0/1
        ip ospf cost 10
    R2 undo:
        interface Ethernet0/1
        no ip ospf cost

Example: make ospf notice failures faster on the link between R5 and R6
    Plan: OSPF hello 5 s / dead 20 s on both ends of the R5-R6 link (both ends must match)
    R5 config:
        interface Ethernet0/0
        ip ospf hello-interval 5
        ip ospf dead-interval 20
    R5 undo:
        interface Ethernet0/0
        no ip ospf hello-interval
        no ip ospf dead-interval
    R6 config:
        interface Ethernet0/0
        ip ospf hello-interval 5
        ip ospf dead-interval 20
    R6 undo:
        interface Ethernet0/0
        no ip ospf hello-interval
        no ip ospf dead-interval

## Share the default route
- default-information originate: gives the router's default route to all OSPF routers.

Example: share EDGE's default route with all ospf routers
    Plan: EDGE announces its default route into OSPF (default-information originate)
    EDGE config:
        router ospf 1
        default-information originate
    EDGE undo:
        router ospf 1
        no default-information originate

## Stop advertising a network
- router ospf 1 + no network ... area 0 (the same line with "no").

Example: stop advertising 192.168.50.0/24 in ospf on R5
    Plan: Remove 192.168.50.0/24 from OSPF on R5 (the rollback adds it back)
    R5 config:
        router ospf 1
        no network 192.168.50.0 0.0.0.255 area 0
    R5 undo:
        router ospf 1
        network 192.168.50.0 0.0.0.255 area 0

## Check OSPF
Check: show ip ospf neighbor (FULL = OK), show ip ospf interface brief, show ip route ospf.

Example: are the ospf neighbors of R2 up?
    Plan: Show R2's OSPF neighbors (state FULL = working)
    R2 check:
        show ip ospf neighbor

Example: show which interfaces of R5 run ospf
    Plan: Show R5's OSPF interfaces, areas and costs
    R5 check:
        show ip ospf interface brief

Example: show the ospf part of R6's configuration
    Plan: Show only the OSPF section of R6's running config
    R6 check:
        show running-config | section router ospf
