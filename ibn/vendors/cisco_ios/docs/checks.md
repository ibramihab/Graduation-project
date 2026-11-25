# Read-only check commands (Cisco IOS)

## Rules for checks
- Check commands start with show, ping or traceroute: step type "check", rollback [].
- Never put them in a "config" step, and never put configuration in a "check" step.
- Interfaces: show ip interface brief, show interfaces <name>, show interfaces status.
- Config: show running-config | section <word>, show running-config interface <name>.
- Services: show access-lists, show ip nat translations, show ip dhcp binding, show standby brief.

## Can one device or network reach another
- ping <ip>, ping <ip> source <my interface ip>, ping <ip> repeat 100, traceroute <ip>.
- "Can network A reach B?": ping from A's gateway router WITH source = A's gateway address.

Example: can R1 reach R2?
    Plan: Ping R2's address on the R1-R2 link from R1
    R1 check:
        ping 10.0.12.2

Example: test if the 192.168.10.0 network behind R1 can reach the server 172.16.1.10
    Plan: Ping and trace to the server from R1, using R1's address in 192.168.10.0/24 as the source
    R1 check:
        ping 172.16.1.10 source 192.168.10.1
        traceroute 172.16.1.10 source 192.168.10.1

## Routing table
- show ip route, show ip route <address>, show ip protocols.

Example: show the routing table of R3
    Plan: Show R3's routing table
    R3 check:
        show ip route

Example: اعرض جدول الروتنج في R1
    Plan: Show R1's routing table
    R1 check:
        show ip route

## Neighbors and learned addresses
- show cdp neighbors (which device is on which port), show mac address-table, show spanning-tree.

Example: which devices are connected to SW2?
    Plan: Show SW2's CDP neighbors (device, local port, remote port)
    SW2 check:
        show cdp neighbors

Example: which mac addresses has SW1 learned?
    Plan: Show SW1's MAC address table
    SW1 check:
        show mac address-table

## Find why something can't be reached
- Check the route on each router on the way, then ping step by step.

Example: why can't the 192.168.50.0/24 network reach 10.70.0.5?
    Plan: Check the route, the path and the filters from R5 (using its 192.168.50.0/24 address as source)
    R5 check:
        show ip route 10.70.0.5
        ping 10.70.0.5 source 192.168.50.1
        traceroute 10.70.0.5 source 192.168.50.1
    R7 check:
        show access-lists
