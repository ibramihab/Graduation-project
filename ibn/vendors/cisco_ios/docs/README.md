# Cisco IOS knowledge for the AI (RAG)

One file per topic (static_routes, ospf, acl, vlans_trunks, interfaces, dhcp_nat, switch_protection,
services, checks, masks, safety). Each `## ` heading is ONE piece the AI can get: a short note and
up to 3 solved examples. New or changed files are picked up by themselves.

## The format (follow it exactly: a test checks it)
```
## Static route to a network
Syntax: ip route <network> <subnet mask> <next hop>
- A short rule in our own words.

Example: on R1 add a static route to 192.168.2.0/24 via R2
    Plan: Static route on R1 to 192.168.2.0/24 through R2
    R1 config:
        ip route 192.168.2.0 255.255.255.0 10.0.12.2
    R1 undo:
        no ip route 192.168.2.0 255.255.255.0 10.0.12.2

Example: restart R2
    Refuse: reloading a device is blocked, because the program would lose it.
```
- `Example:` = what a user would type (English or Arabic).
- `Plan:` = one line saying what the plan does (optional).
- `<device> config:` = configuration commands; every one needs `<device> undo:` right after.
- `<device> check:` = read-only commands (show, ping, traceroute); no undo.
- `Refuse:` = a request that must be refused, with the reason.
- 4 spaces before `Plan`/`R1 config:`, 8 spaces before each command.
- At most 3 examples per heading. For a new case, add a new heading.

## Pasted vendor pages
`.txt` files = text pasted from cisco.com (Command Reference / Configuration Guide). They stay on
YOUR laptop only (copyright and size): they are never uploaded to GitHub. Copy only the syntax,
the "no" form and a short example. They are cut into pieces of about 1200 characters.
