# VLANs, access ports, trunks (Cisco IOS switch)
- Create: vlan 10 + name Sales. Several: vlan 100-105. Delete: no vlan 10. VLAN 1 can't be deleted.
- Access port: interface Ethernet0/1 + switchport mode access + switchport access vlan 10.
  Undo: no switchport access vlan 10 + no switchport mode access.
- Trunk (IOL switches need the encapsulation first):
  interface Ethernet0/0 + switchport trunk encapsulation dot1q + switchport mode trunk.
  Undo: no switchport mode trunk + no switchport trunk encapsulation dot1q.
- Allowed VLANs: switchport trunk allowed vlan 10,20 (replace list) / allowed vlan add 30 / remove 30.
  Back to all: switchport trunk allowed vlan all.
- Native VLAN (same on both ends): switchport trunk native vlan 99. Undo: no switchport trunk native vlan.
- Voice VLAN for an IP phone: switchport voice vlan 150.
- Routing between VLANs on a router (router on a stick): interface Ethernet0/1.10 + encapsulation dot1Q 10 +
  ip address <gateway of VLAN 10> <mask>; the switch port to the router must be a trunk.
Check: show vlan brief, show interfaces trunk, show interfaces status.
