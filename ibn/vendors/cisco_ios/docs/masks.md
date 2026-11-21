# Subnet masks and wildcard masks
/8  = 255.0.0.0         wildcard 0.255.255.255
/16 = 255.255.0.0       wildcard 0.0.255.255
/24 = 255.255.255.0     wildcard 0.0.0.255     (254 hosts)
/25 = 255.255.255.128   wildcard 0.0.0.127
/26 = 255.255.255.192   wildcard 0.0.0.63
/27 = 255.255.255.224   wildcard 0.0.0.31
/28 = 255.255.255.240   wildcard 0.0.0.15
/29 = 255.255.255.248   wildcard 0.0.0.7
/30 = 255.255.255.252   wildcard 0.0.0.3       (2 hosts: router links)
/32 = 255.255.255.255   wildcard 0.0.0.0       (one address; in access lists write "host <ip>")
Where each is used:
- SUBNET MASK: ip address, ip route, DHCP "network", NAT addresses.
- WILDCARD: OSPF "network", EIGRP "network", access lists.
- Wildcard = 255.255.255.255 minus the mask.
