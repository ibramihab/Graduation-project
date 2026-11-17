# Cisco IOS documentation for the AI (RAG)

Put Cisco documentation here as plain text, one file per feature, e.g.:
```
static_routes.txt   ospf.txt   acl.txt   vlan_trunk.txt   dhcp.txt   nat.txt
```
How: open the page on cisco.com (Command Reference / Configuration Guide, IOS 15 when offered),
select the text, paste it into a .txt file here, save as UTF-8.

- The program cuts each file into small pieces and sends the AI only the pieces closest to the
  request (RAG source "docs"). New or changed files are picked up by themselves.
- These files stay on your laptop: they are NOT uploaded to GitHub (copyright and size).
  Each teammate who wants them puts them in their own copy.
- Copy only the parts you need (syntax, parameters, the "no" form, a short example):
  short, clean text helps the AI more than whole pages.
