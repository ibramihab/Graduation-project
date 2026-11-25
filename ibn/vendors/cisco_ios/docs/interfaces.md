# Interfaces (Cisco IOS)

## IP address on an interface
- Always: "interface <name>" first, then its settings on the next lines.
- Use the real names of the device (IOL: Ethernet0/0, Ethernet0/1 ... not GigabitEthernet).
- ip address 10.0.25.1 255.255.255.0 (a subnet mask, not /24), then no shutdown.
- Undo: no ip address (or put back the old address) + shutdown.
- An interface can't get the network address (.0 for /24) or the broadcast address (.255 for /24).
- Two interfaces of the same router can't be in the same subnet.

Example: give R2 interface e0/2 the address 10.0.25.1/24 and turn it on
    Plan: Set 10.0.25.1/24 on R2 Ethernet0/2 and enable it
    R2 config:
        interface Ethernet0/2
        ip address 10.0.25.1 255.255.255.0
        no shutdown
    R2 undo:
        interface Ethernet0/2
        no ip address
        shutdown

Example: give R7 port e0/2 the address 10.0.78.1/30 for the new link to R8
    Plan: Set 10.0.78.1/30 on R7 Ethernet0/2 (a /30 link has 2 usable addresses) and enable it
    R7 config:
        interface Ethernet0/2
        ip address 10.0.78.1 255.255.255.252
        no shutdown
    R7 undo:
        interface Ethernet0/2
        no ip address
        shutdown

## Second address
- Extra address: ip address <ip> <mask> secondary.

Example: add a second address 192.168.51.1/24 on R5 e0/1
    Plan: Secondary address 192.168.51.1/24 on R5 Ethernet0/1
    R5 config:
        interface Ethernet0/1
        ip address 192.168.51.1 255.255.255.0 secondary
    R5 undo:
        interface Ethernet0/1
        no ip address 192.168.51.1 255.255.255.0 secondary

## Turn an interface off or on
- shutdown / no shutdown.

Example: shut down port e0/3 on SW2
    Plan: Turn off Ethernet0/3 on SW2
    SW2 config:
        interface Ethernet0/3
        shutdown
    SW2 undo:
        interface Ethernet0/3
        no shutdown

Example: bring interface e0/1 on R3 back up
    Plan: Turn on Ethernet0/1 on R3
    R3 config:
        interface Ethernet0/1
        no shutdown
    R3 undo:
        interface Ethernet0/1
        shutdown

## Description
- description <text> (undo: no description).

Example: label R1's port e0/0 as 'link to ISP'
    Plan: Add a description on R1 Ethernet0/0
    R1 config:
        interface Ethernet0/0
        description link to ISP
    R1 undo:
        interface Ethernet0/0
        no description

## Loopback
- interface Loopback1 + ip address 1.1.1.1 255.255.255.255. Undo: no interface Loopback1.

Example: create loopback 1 with ip 1.1.1.1/32 on R1
    Plan: Create Loopback1 on R1 with 1.1.1.1/32
    R1 config:
        interface Loopback1
        ip address 1.1.1.1 255.255.255.255
    R1 undo:
        no interface Loopback1

## Shared gateway (HSRP)
- On both routers: interface + standby 1 ip <virtual gateway IP>.
- The active router gets a higher priority (standby 1 priority 110) and standby 1 preempt.
- Undo: no standby 1 on the interface.

Example: make R5 and R6 share the gateway 192.168.50.254 with hsrp, R5 active
    Plan: HSRP group 1 with virtual IP 192.168.50.254: R5 active (priority 110, preempt), R6 standby
    R5 config:
        interface Ethernet0/1
        standby 1 ip 192.168.50.254
        standby 1 priority 110
        standby 1 preempt
    R5 undo:
        interface Ethernet0/1
        no standby 1
    R6 config:
        interface Ethernet0/1
        standby 1 ip 192.168.50.254
    R6 undo:
        interface Ethernet0/1
        no standby 1

## Check interfaces
Check: show ip interface brief, show interfaces <name>, show running-config interface <name>.

Example: which interfaces of R2 are up and what are their ips?
    Plan: Show R2's interfaces with their IP and status
    R2 check:
        show ip interface brief
