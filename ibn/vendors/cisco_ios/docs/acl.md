# Access lists (Cisco IOS)

## Block one network from another
Extended named list (source AND destination):
- ip access-list extended NAME
- deny ip <source> <wildcard> <destination> <wildcard>       e.g. deny ip 10.1.1.0 0.0.0.255 10.2.2.0 0.0.0.255
- END WITH: permit ip any any   (an access list ends with a hidden "deny everything")
- Apply it on an interface: interface Ethernet0/1 + ip access-group NAME in (or out).
- "in" = traffic arriving on that port; "out" = traffic leaving it. Put it close to the traffic you block.

Example: block the 192.168.3.0/24 network from reaching 192.168.2.0/24
    Plan: On R2, drop traffic from 192.168.3.0/24 to 192.168.2.0/24 arriving from R1; everything else is allowed
    R2 config:
        ip access-list extended BLOCK_3_TO_2
        deny ip 192.168.3.0 0.0.0.255 192.168.2.0 0.0.0.255
        permit ip any any
        interface Ethernet0/0
        ip access-group BLOCK_3_TO_2 in
    R2 undo:
        interface Ethernet0/0
        no ip access-group BLOCK_3_TO_2 in
        no ip access-list extended BLOCK_3_TO_2

Example: امنع شبكة 10.30.0.0/24 انها توصل لشبكة 10.40.0.0/24
    Plan: On R2, drop traffic from 10.30.0.0/24 to 10.40.0.0/24; everything else is allowed
    R2 config:
        ip access-list extended BLOCK_30_TO_40
        deny ip 10.30.0.0 0.0.0.255 10.40.0.0 0.0.0.255
        permit ip any any
        interface Ethernet0/1
        ip access-group BLOCK_30_TO_40 in
    R2 undo:
        interface Ethernet0/1
        no ip access-group BLOCK_30_TO_40 in
        no ip access-list extended BLOCK_30_TO_40

## Block one device
- One address: "host 10.0.0.5"; everything: "any".

Example: the pc 192.168.10.25 must not reach the server 172.16.1.10
    Plan: On R1, drop traffic from host 192.168.10.25 to host 172.16.1.10 arriving on the LAN port
    R1 config:
        ip access-list extended PC25_NOT_TO_SERVER
        deny ip host 192.168.10.25 host 172.16.1.10
        permit ip any any
        interface Ethernet0/1
        ip access-group PC25_NOT_TO_SERVER in
    R1 undo:
        interface Ethernet0/1
        no ip access-group PC25_NOT_TO_SERVER in
        no ip access-list extended PC25_NOT_TO_SERVER

Example: the guest pc 192.168.70.9 must not reach anything outside its own network
    Plan: On R7, drop all traffic from host 192.168.70.9 arriving on the LAN port; others are not affected
    R7 config:
        ip access-list extended BLOCK_GUEST_9
        deny ip host 192.168.70.9 any
        permit ip any any
        interface Ethernet0/1
        ip access-group BLOCK_GUEST_9 in
    R7 undo:
        interface Ethernet0/1
        no ip access-group BLOCK_GUEST_9 in
        no ip access-list extended BLOCK_GUEST_9

Example: امنع الجهاز 192.168.70.20 يدخل على السيرفر 10.70.0.5
    Plan: On R7, drop traffic from 192.168.70.20 to the server 10.70.0.5; everything else is allowed
    R7 config:
        ip access-list extended PC20_NOT_TO_SRV
        deny ip host 192.168.70.20 host 10.70.0.5
        permit ip any any
        interface Ethernet0/1
        ip access-group PC20_NOT_TO_SRV in
    R7 undo:
        interface Ethernet0/1
        no ip access-group PC20_NOT_TO_SRV in
        no ip access-list extended PC20_NOT_TO_SRV

## Block a service (port)
- deny tcp <source> <wildcard> any eq 23     ports: ssh 22, telnet 23, dns 53 (udp), http 80, https 443
- deny icmp any host 10.0.0.5                 ping

Example: block telnet and ssh to the routers from the 10.20.0.0/24 network on R4
    Plan: On R4, drop remote logins (telnet 23, ssh 22) from 10.20.0.0/24; other traffic is allowed
    R4 config:
        ip access-list extended NO_LOGIN_FROM_20
        deny tcp 10.20.0.0 0.0.0.255 any eq 23
        deny tcp 10.20.0.0 0.0.0.255 any eq 22
        permit ip any any
        interface Ethernet0/2
        ip access-group NO_LOGIN_FROM_20 in
    R4 undo:
        interface Ethernet0/2
        no ip access-group NO_LOGIN_FROM_20 in
        no ip access-list extended NO_LOGIN_FROM_20

Example: block dns (udp 53) from 192.168.60.0/24 to any server, everything else allowed
    Plan: On R6, drop DNS queries (udp 53) coming from 192.168.60.0/24; all other traffic is allowed
    R6 config:
        ip access-list extended NO_DNS_60
        deny udp 192.168.60.0 0.0.0.255 any eq 53
        permit ip any any
        interface Ethernet0/1
        ip access-group NO_DNS_60 in
    R6 undo:
        interface Ethernet0/1
        no ip access-group NO_DNS_60 in
        no ip access-list extended NO_DNS_60

Example: stop everyone from pinging R2's loopback 2.2.2.2
    Plan: On R2, drop ping (icmp) to 2.2.2.2 arriving on its links; everything else is allowed
    R2 config:
        ip access-list extended NO_PING_LOOPBACK
        deny icmp any host 2.2.2.2
        permit ip any any
        interface Ethernet0/0
        ip access-group NO_PING_LOOPBACK in
    R2 undo:
        interface Ethernet0/0
        no ip access-group NO_PING_LOOPBACK in
        no ip access-list extended NO_PING_LOOPBACK

## Allow only some sources
- Order matters: lines are checked top to bottom, the first match wins.
- Put the permit for the allowed source BEFORE the deny for everyone else.

Example: only the 192.168.5.0/24 network may open the web server 172.16.9.80, block web for everyone else
    Plan: On R3, in front of the server: allow web (tcp 80) from 192.168.5.0/24 only, block web from others, allow the rest
    R3 config:
        ip access-list extended WEB_ONLY_FROM_5
        permit tcp 192.168.5.0 0.0.0.255 host 172.16.9.80 eq 80
        deny tcp any host 172.16.9.80 eq 80
        permit ip any any
        interface Ethernet0/1
        ip access-group WEB_ONLY_FROM_5 out
    R3 undo:
        interface Ethernet0/1
        no ip access-group WEB_ONLY_FROM_5 out
        no ip access-list extended WEB_ONLY_FROM_5

## Limit remote login (SSH) to the device
Standard list (source only): ip access-list standard NAME + permit <net> <wildcard>,
applied with: line vty 0 4 + access-class NAME in. Always keep the management network allowed.

Example: allow ssh to R5 only from the admin network 10.250.0.0/24
    Plan: Standard ACL on R5's VTY lines: only 10.250.0.0/24 may log in remotely
    R5 config:
        ip access-list standard VTY_ADMINS
        permit 10.250.0.0 0.0.0.255
        line vty 0 4
        access-class VTY_ADMINS in
    R5 undo:
        line vty 0 4
        no access-class VTY_ADMINS in
        no ip access-list standard VTY_ADMINS

## Change or remove an access list
- Edit one line: ip access-list extended NAME + "15 deny ..." (number = position), remove with "no 15".
- A deny after "permit ip any any" never matches: insert it with a smaller line number.
- Undo: first "no ip access-group NAME in" on the interface, then "no ip access-list extended NAME".

Example: also block 192.168.3.77 in the access list BLOCK_3_TO_2 on R2
    Plan: Insert a deny line (sequence 5) at the top of BLOCK_3_TO_2 on R2
    R2 config:
        ip access-list extended BLOCK_3_TO_2
        5 deny ip host 192.168.3.77 any
    R2 undo:
        ip access-list extended BLOCK_3_TO_2
        no 5

Example: remove the access list BLOCK_3_TO_2 from R2
    Plan: Take BLOCK_3_TO_2 off R2's Ethernet0/0, then delete it (the rollback puts it back)
    R2 config:
        interface Ethernet0/0
        no ip access-group BLOCK_3_TO_2 in
        no ip access-list extended BLOCK_3_TO_2
    R2 undo:
        ip access-list extended BLOCK_3_TO_2
        deny ip 192.168.3.0 0.0.0.255 192.168.2.0 0.0.0.255
        permit ip any any
        interface Ethernet0/0
        ip access-group BLOCK_3_TO_2 in

## Check access lists
Check: show access-lists (match counters), show ip interface <port>.

Example: which access lists are on R3 and are they matching packets?
    Plan: Show R3's access lists with their match counters
    R3 check:
        show access-lists
