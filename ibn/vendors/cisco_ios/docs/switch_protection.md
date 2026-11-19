# Switch protection: port security, spanning tree, EtherChannel (Cisco IOS)
Port security (access ports only):
- switchport mode access + switchport port-security + switchport port-security maximum 1
  + switchport port-security mac-address sticky (remember the current device)
- A violation shuts the port (err-disabled). Recover: shutdown + no shutdown, or errdisable recovery.
- Never on ports to routers or other switches.
Spanning tree:
- spanning-tree portfast + spanning-tree bpduguard enable: only on ports to PCs.
- Root bridge for a VLAN: spanning-tree vlan 10 priority 4096 (lowest wins). Undo: no spanning-tree vlan 10 priority.
- Faster mode: spanning-tree mode rapid-pvst (default: pvst).
EtherChannel (LACP), same on both switches:
- interface Ethernet0/2 + channel-group 1 mode active (and the same for every member port)
- Configure trunk/VLANs on interface Port-channel1, not on the members.
- Undo: no channel-group 1 on each member, then no interface Port-channel1.
Check: show port-security, show spanning-tree, show etherchannel summary.
