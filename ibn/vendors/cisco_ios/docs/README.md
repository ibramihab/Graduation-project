# Cisco IOS documentation for the AI (RAG)

The program cuts these files into small pieces and gives the AI only the pieces closest to the
request (RAG source "docs"). New or changed files are picked up by themselves.

Two kinds of files:
- **`.md` = our own short notes** (written in our own words: commands, the "no" form, common mistakes).
  They are on GitHub, so the whole team has them: static_routes, ospf, acl, vlans_trunks, interfaces,
  dhcp_nat, switch_protection, checks, masks, safety.
- **`.txt` = text you paste from cisco.com** (Command Reference / Configuration Guide). They stay on
  YOUR laptop only (copyright and size): they are never uploaded to GitHub.

Short and clean text helps the AI more than whole pages: copy only the syntax, the parameters,
the "no" form and a short example.
