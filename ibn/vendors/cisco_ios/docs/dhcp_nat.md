# DHCP and NAT (Cisco IOS)

## DHCP server on a router
- ip dhcp excluded-address <first> <last>     (FIRST: keep addresses for gateway, switches, servers)
- ip dhcp pool NAME + network <network> <SUBNET MASK> + default-router <gateway> + dns-server <ip>
  (here "network" uses a normal mask like 255.255.255.0, not a wildcard)
- Undo: no ip dhcp pool NAME + no ip dhcp excluded-address <first> <last>

Example: make R1 give addresses to the 192.168.10.0/24 network, keep the first 10 for devices
    Plan: DHCP pool LAN10 on R1: 192.168.10.0/24, gateway 192.168.10.1, addresses .1-.10 kept for equipment
    R1 config:
        ip dhcp excluded-address 192.168.10.1 192.168.10.10
        ip dhcp pool LAN10
        network 192.168.10.0 255.255.255.0
        default-router 192.168.10.1
        dns-server 8.8.8.8
    R1 undo:
        no ip dhcp pool LAN10
        no ip dhcp excluded-address 192.168.10.1 192.168.10.10

Example: give the pcs of 10.60.1.0/24 behind R6 addresses automatically, gateway 10.60.1.1, dns 1.1.1.1
    Plan: DHCP pool PCS on R6 for 10.60.1.0/24, gateway 10.60.1.1, DNS 1.1.1.1, first 20 addresses kept for equipment
    R6 config:
        ip dhcp excluded-address 10.60.1.1 10.60.1.20
        ip dhcp pool PCS
        network 10.60.1.0 255.255.255.0
        default-router 10.60.1.1
        dns-server 1.1.1.1
    R6 undo:
        no ip dhcp pool PCS
        no ip dhcp excluded-address 10.60.1.1 10.60.1.20

## DHCP relay
- The server is on another network: on the PCs' gateway interface: ip helper-address <server IP>.

Example: the pcs behind R3 e0/2 should get their addresses from the dhcp server 10.0.12.1
    Plan: DHCP relay on R3 Ethernet0/2: forward the PCs' DHCP requests to 10.0.12.1
    R3 config:
        interface Ethernet0/2
        ip helper-address 10.0.12.1
    R3 undo:
        interface Ethernet0/2
        no ip helper-address 10.0.12.1

## NAT for many PCs (PAT)
- Mark ports: inside network port "ip nat inside", internet port "ip nat outside".
- access-list 10 permit <inside net> <wildcard> + ip nat inside source list 10 interface <outside port> overload
- Undo in reverse: the "ip nat inside source ..." line with "no", then the interface marks, then the access list.

Example: let the inside network 192.168.0.0/16 reach the internet through R1 e0/0 using pat
    Plan: PAT on R1: inside = Ethernet0/1, outside = Ethernet0/0, translate 192.168.0.0/16 to Ethernet0/0's address
    R1 config:
        access-list 10 permit 192.168.0.0 0.0.255.255
        interface Ethernet0/1
        ip nat inside
        interface Ethernet0/0
        ip nat outside
        ip nat inside source list 10 interface Ethernet0/0 overload
    R1 undo:
        no ip nat inside source list 10 interface Ethernet0/0 overload
        interface Ethernet0/1
        no ip nat inside
        interface Ethernet0/0
        no ip nat outside
        no access-list 10

## Static NAT and port forwarding
- One server, fixed outside address: ip nat inside source static <inside ip> <outside ip>
- Port forwarding: ip nat inside source static tcp <inside ip> <port> interface <outside port> <outside port number>

Example: make the web server 192.168.80.10 reachable from outside as 203.0.113.10 on EDGE
    Plan: Static NAT on EDGE: 192.168.80.10 <-> 203.0.113.10 (inside e0/1, outside e0/0)
    EDGE config:
        interface Ethernet0/1
        ip nat inside
        interface Ethernet0/0
        ip nat outside
        ip nat inside source static 192.168.80.10 203.0.113.10
    EDGE undo:
        no ip nat inside source static 192.168.80.10 203.0.113.10
        interface Ethernet0/1
        no ip nat inside
        interface Ethernet0/0
        no ip nat outside

Example: forward port 8080 on EDGE's outside interface to the camera 192.168.80.50 port 80
    Plan: Port forwarding on EDGE: outside Ethernet0/0 tcp 8080 -> 192.168.80.50 tcp 80
    EDGE config:
        interface Ethernet0/1
        ip nat inside
        interface Ethernet0/0
        ip nat outside
        ip nat inside source static tcp 192.168.80.50 80 interface Ethernet0/0 8080
    EDGE undo:
        no ip nat inside source static tcp 192.168.80.50 80 interface Ethernet0/0 8080
        interface Ethernet0/1
        no ip nat inside
        interface Ethernet0/0
        no ip nat outside

## Check DHCP and NAT
Check: show ip dhcp binding, show ip dhcp pool, show ip nat translations, show ip nat statistics.

Example: is nat working on EDGE?
    Plan: Show EDGE's NAT translations and counters
    EDGE check:
        show ip nat translations
        show ip nat statistics

Example: which addresses did the dhcp server on R6 give out?
    Plan: Show R6's DHCP bindings and pool usage
    R6 check:
        show ip dhcp binding
        show ip dhcp pool
