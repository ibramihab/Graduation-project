# Access lists (Cisco IOS)
Extended named list (source AND destination, protocol, port):
- ip access-list extended NAME
- deny ip <source> <wildcard> <destination> <wildcard>       e.g. deny ip 10.1.1.0 0.0.0.255 10.2.2.0 0.0.0.255
- deny tcp <source> <wildcard> any eq 23                     ports: ssh 22, telnet 23, dns 53 (udp), http 80, https 443
- deny icmp any host 10.0.0.5                                 ping
- one address: "host 10.0.0.5"; everything: "any"
- END WITH: permit ip any any   (an access list ends with a hidden "deny everything")
Apply it on an interface: interface Ethernet0/1 + ip access-group NAME in (or out).
- "in" = traffic arriving on that port; "out" = traffic leaving it.
- Put it close to the traffic you block, on every port that traffic can use.
Order matters: lines are checked top to bottom, the first match wins; a deny after "permit ip any any" never matches.
Edit one line: ip access-list extended NAME + "15 deny ..." (number = position), remove with "no 15".
Undo: first "no ip access-group NAME in" on the interface, then "no ip access-list extended NAME".
Standard list (source only), e.g. to limit SSH: ip access-list standard NAME + permit <net> <wildcard>,
applied with: line vty 0 4 + access-class NAME in. Always keep the management network allowed.
Check: show access-lists (match counters), show ip interface <port>.
