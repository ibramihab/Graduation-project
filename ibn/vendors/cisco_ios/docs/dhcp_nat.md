# DHCP and NAT (Cisco IOS)
DHCP server on a router:
- ip dhcp excluded-address <first> <last>     (FIRST: keep addresses for gateway, switches, servers)
- ip dhcp pool NAME + network <network> <SUBNET MASK> + default-router <gateway> + dns-server <ip>
  (here "network" uses a normal mask like 255.255.255.0, not a wildcard)
- Undo: no ip dhcp pool NAME + no ip dhcp excluded-address <first> <last>
DHCP relay (the server is on another network): on the PCs' gateway interface: ip helper-address <server IP>.
Check: show ip dhcp binding, show ip dhcp pool.

NAT:
- Mark ports: inside network port "ip nat inside", internet port "ip nat outside".
- PAT (many PCs share one outside address): access-list 10 permit <inside net> <wildcard>
  + ip nat inside source list 10 interface <outside port> overload
- Static NAT (one server, fixed outside address): ip nat inside source static <inside ip> <outside ip>
- Port forwarding: ip nat inside source static tcp <inside ip> <port> interface <outside port> <outside port number>
- Undo in reverse: the "ip nat inside source ..." line with "no", then the interface marks, then the access list.
Check: show ip nat translations, show ip nat statistics.
