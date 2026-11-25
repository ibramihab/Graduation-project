# VLANs, access ports, trunks (Cisco IOS switch)

## Create a VLAN
- Create: vlan 10 + name Sales. Several: vlan 100-105. Undo: no vlan 10.

Example: I need a vlan 30 for the guests on both switches SW1 and SW2
    Plan: Create VLAN 30 named Guests on SW1 and SW2
    SW1 config:
        vlan 30
        name Guests
    SW1 undo:
        no vlan 30
    SW2 config:
        vlan 30
        name Guests
    SW2 undo:
        no vlan 30

Example: اعمل فيلان 40 اسمها IT على SW1
    Plan: Create VLAN 40 named IT on SW1
    SW1 config:
        vlan 40
        name IT
    SW1 undo:
        no vlan 40

Example: create vlans 100 to 105 on SW2
    Plan: Create VLANs 100-105 on SW2 in one command
    SW2 config:
        vlan 100-105
    SW2 undo:
        no vlan 100-105

## Put a port in a VLAN
- Access port: interface Ethernet0/1 + switchport mode access + switchport access vlan 10.
- Undo: no switchport access vlan 10 + no switchport mode access.

Example: create vlan 10 named Sales on SW1 and put port e0/1 in it
    Plan: Create VLAN 10 (Sales) on SW1 and make Ethernet0/1 an access port in it
    SW1 config:
        vlan 10
        name Sales
        interface Ethernet0/1
        switchport mode access
        switchport access vlan 10
    SW1 undo:
        interface Ethernet0/1
        no switchport access vlan 10
        no switchport mode access
        no vlan 10

Example: connect the printer on SW2 port e0/3 to vlan 20
    Plan: Make Ethernet0/3 on SW2 an access port in VLAN 20
    SW2 config:
        interface Ethernet0/3
        switchport mode access
        switchport access vlan 20
    SW2 undo:
        interface Ethernet0/3
        no switchport access vlan 20
        no switchport mode access

Example: حط البورت e0/3 في SW2 على فيلان 20
    Plan: Make Ethernet0/3 on SW2 an access port in VLAN 20
    SW2 config:
        interface Ethernet0/3
        switchport mode access
        switchport access vlan 20
    SW2 undo:
        interface Ethernet0/3
        no switchport access vlan 20
        no switchport mode access

## Rename or delete a VLAN
- Rename: vlan 10 + name <new name>. Delete: no vlan 10. VLAN 1 can't be deleted.

Example: rename vlan 10 on SW1 to Marketing
    Plan: Change the name of VLAN 10 on SW1 to Marketing
    SW1 config:
        vlan 10
        name Marketing
    SW1 undo:
        vlan 10
        no name

Example: delete vlan 30 from SW2
    Plan: Remove VLAN 30 from SW2 (the rollback creates it again)
    SW2 config:
        no vlan 30
    SW2 undo:
        vlan 30

## Make a port a trunk
- IOL switches need the encapsulation first:
  interface Ethernet0/0 + switchport trunk encapsulation dot1q + switchport mode trunk.
- Undo: no switchport mode trunk + no switchport trunk encapsulation dot1q.

Example: make the link from SW1 e0/0 to the router a trunk
    Plan: Make Ethernet0/0 on SW1 an 802.1Q trunk (IOL switches need the encapsulation first)
    SW1 config:
        interface Ethernet0/0
        switchport trunk encapsulation dot1q
        switchport mode trunk
    SW1 undo:
        interface Ethernet0/0
        no switchport mode trunk
        no switchport trunk encapsulation dot1q

## Allowed and native VLANs on a trunk
- Allowed VLANs: switchport trunk allowed vlan 10,20 (replace list) / allowed vlan add 30 / remove 30.
  Back to all: switchport trunk allowed vlan all.
- Native VLAN (same on both ends): switchport trunk native vlan 99. Undo: no switchport trunk native vlan.

Example: let only vlans 10 and 20 pass on the trunk e0/0 of SW1
    Plan: Limit the trunk Ethernet0/0 on SW1 to VLANs 10 and 20
    SW1 config:
        interface Ethernet0/0
        switchport trunk allowed vlan 10,20
    SW1 undo:
        interface Ethernet0/0
        switchport trunk allowed vlan all

Example: also allow vlan 30 on the trunk e0/0 of SW1
    Plan: Add VLAN 30 to the allowed list of SW1's trunk Ethernet0/0
    SW1 config:
        interface Ethernet0/0
        switchport trunk allowed vlan add 30
    SW1 undo:
        interface Ethernet0/0
        switchport trunk allowed vlan remove 30

Example: set the native vlan of the trunk e0/0 on SW2 to 99
    Plan: Native VLAN 99 on SW2's trunk Ethernet0/0 (set the same on the other end)
    SW2 config:
        interface Ethernet0/0
        switchport trunk native vlan 99
    SW2 undo:
        interface Ethernet0/0
        no switchport trunk native vlan

## Voice VLAN
- Voice VLAN for an IP phone: switchport voice vlan 150.

Example: add a voice vlan 150 for the ip phone on SW1 port e0/2
    Plan: Voice VLAN 150 on SW1 Ethernet0/2 (the PC behind the phone stays in its data VLAN)
    SW1 config:
        vlan 150
        name Voice
        interface Ethernet0/2
        switchport voice vlan 150
    SW1 undo:
        interface Ethernet0/2
        no switchport voice vlan 150
        no vlan 150

## Routing between VLANs (router on a stick)
- interface Ethernet0/1.10 + encapsulation dot1Q 10 + ip address <gateway of VLAN 10> <mask>.
- The switch port to the router must be a trunk.

Example: route between vlan 10 (192.168.10.0/24) and vlan 20 (192.168.20.0/24) on R1 using its port e0/1 to the switch
    Plan: Router-on-a-stick on R1: one subinterface per VLAN on Ethernet0/1, gateways .1 (the switch port must be a trunk)
    R1 config:
        interface Ethernet0/1.10
        encapsulation dot1Q 10
        ip address 192.168.10.1 255.255.255.0
        interface Ethernet0/1.20
        encapsulation dot1Q 20
        ip address 192.168.20.1 255.255.255.0
    R1 undo:
        no interface Ethernet0/1.10
        no interface Ethernet0/1.20

## Check VLANs and trunks
Check: show vlan brief, show interfaces trunk, show interfaces status.

Example: show the vlans on SW1 and SW2
    Plan: Show the VLAN list on both switches
    SW1 check:
        show vlan brief
    SW2 check:
        show vlan brief

Example: show the trunks of SW1
    Plan: Show SW1's trunk ports and their allowed VLANs
    SW1 check:
        show interfaces trunk

Example: create vlan 50 on SW2, put e0/2 in it, then show the vlans
    Plan: Create VLAN 50 on SW2, make Ethernet0/2 an access port in it, then check
    SW2 config:
        vlan 50
        interface Ethernet0/2
        switchport mode access
        switchport access vlan 50
    SW2 undo:
        interface Ethernet0/2
        no switchport access vlan 50
        no switchport mode access
        no vlan 50
    SW2 check:
        show vlan brief
