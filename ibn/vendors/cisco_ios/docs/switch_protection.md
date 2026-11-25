# Switch protection: port security, spanning tree, EtherChannel (Cisco IOS)

## Port security
- Access ports only: switchport mode access + switchport port-security + switchport port-security maximum 1
  + switchport port-security mac-address sticky (remember the current device)
- A violation shuts the port (err-disabled). Recover: shutdown + no shutdown, or errdisable recovery.
- Never on ports to routers or other switches.

Example: let only the pc that is plugged in now use port e0/1 of SW2
    Plan: Port security on SW2 Ethernet0/1: remember the current MAC (sticky), maximum 1
    SW2 config:
        interface Ethernet0/1
        switchport mode access
        switchport port-security
        switchport port-security mac-address sticky
        switchport port-security maximum 1
    SW2 undo:
        interface Ethernet0/1
        no switchport port-security maximum 1
        no switchport port-security mac-address sticky
        no switchport port-security

## PortFast and BPDU guard
- spanning-tree portfast + spanning-tree bpduguard enable: only on ports to PCs.

Example: enable portfast and bpdu guard on the pc port e0/3 of SW1
    Plan: PortFast + BPDU Guard on SW1 Ethernet0/3 (only for ports to PCs, never to switches)
    SW1 config:
        interface Ethernet0/3
        spanning-tree portfast
        spanning-tree bpduguard enable
    SW1 undo:
        interface Ethernet0/3
        no spanning-tree bpduguard enable
        no spanning-tree portfast

## Root bridge
- spanning-tree vlan 10 priority 4096 (lowest wins). Undo: no spanning-tree vlan 10 priority.
- Faster mode: spanning-tree mode rapid-pvst (default: pvst).

Example: make SW1 the root bridge for vlan 10
    Plan: Lowest spanning-tree priority (4096) for VLAN 10 on SW1, so it becomes the root
    SW1 config:
        spanning-tree vlan 10 priority 4096
    SW1 undo:
        no spanning-tree vlan 10 priority

## EtherChannel (LACP)
- Same on both switches: interface Ethernet0/2 + channel-group 1 mode active (and the same for every member port).
- Configure trunk/VLANs on interface Port-channel1, not on the members.
- Undo: no channel-group 1 on each member, then no interface Port-channel1.

Example: bundle ports e0/2 and e0/3 of SW2 into one lacp etherchannel
    Plan: LACP EtherChannel 1 on SW2 with Ethernet0/2 and Ethernet0/3 (the other switch needs the same)
    SW2 config:
        interface Ethernet0/2
        channel-group 1 mode active
        interface Ethernet0/3
        channel-group 1 mode active
    SW2 undo:
        interface Ethernet0/2
        no channel-group 1
        interface Ethernet0/3
        no channel-group 1
        no interface Port-channel1

## Check switch protection
Check: show port-security, show spanning-tree, show etherchannel summary.
