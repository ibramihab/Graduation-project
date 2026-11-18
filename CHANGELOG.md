# What changed (newest first)

Every change to the project is listed here, so nothing surprises you.
**Type:** 🟢 new · 🟡 changed · 🔴 removed. Files under `docs/` and `README.md` are just text.

---

## Changes after the project guide was written

### Warning when the plan changes a device the user didn't name
- 🟢 `validation/validator.py`: if the request names devices (R1, sw1...) and the plan CHANGES another one, a
  warning: "R1: you didn't name R1 in your request, but the plan changes it". Only device names are compared,
  so it works in any language. No warning when no device is named, or for read-only (check) steps.
  Test: `test_changing_a_device_the_user_didnt_name_warns`.

### Validation warns about missing references
- 🟢 `validation/validator.py`: warnings when a command points at something the device may not have
  (what it has = its last backup + the program's successful changes + this plan):
  - `ip access-group 101 in` / `access-class 10 in` with no access list 101 / 10 (Cisco then filters nothing);
  - `switchport access vlan 60` with no VLAN 60 (a Cisco switch creates it by itself, with no name);
  - `ip route ... 10.9.9.1` when no interface is in 10.9.9.x (needs interfaces saved with masks).
  Test: `test_missing_references_warn`.

### Warning before renaming a VLAN that already exists
- 🟢 Infrastructure: "Find links & IPs" also reads the VLANs of switches (`show vlan brief` on Cisco IOS, NX-OS,
  Arista) and saves them on the device: new fields `vlans` (`["10 HR", "20 Sales"]`) and `vlans_read_at`.
  New optional driver method `get_vlans()` (`drivers/base.py`, `drivers/cli.py`); new vendor fields `show_vlans`
  and `parse_vlans` (`vendors/base.py`). Older drivers without `get_vlans` still work.
- 🟢 `validation/validator.py`: "vlan 10" + "name Sales" while VLAN 10 is "HR" gets a warning
  ("VLAN 10 already exists on sw1 as 'HR': this plan renames it to 'Sales'"). Known VLANs = what the switch said,
  plus the program's own successful changes since then (works on simulated devices too, from the history).
- 🟡 `vendors/cisco_nxos.py`: back to `show ip interface brief` (NX-OS prints `show ip interface` differently, so the
  mask change for IOS had broken NX-OS interface reading).
  Tests: `test_renaming_an_existing_vlan_warns`, `test_vlans_are_read_from_real_switches_and_nxos_interfaces_still_work`.

### Validation refuses IP conflicts
- 🟢 `validation/validator.py`: compared with the IPs the knowledge base knows (from "Find links & IPs" or typed
  by hand), a plan is refused if it gives an IP that's already on another device or interface, reuses another
  device's management IP, gives the same new IP to two devices, or puts two interfaces of ONE device in
  overlapping subnets (a real Cisco refuses that: "% ... overlaps with ..."). Moving an IP in one plan
  (`no ip address` first) is fine. Reads Cisco/Arista/Huawei (`ip address`), FortiGate (`edit` + `set ip`) and
  MikroTik (`address=... interface=...`); works with interfaces saved with or without a mask.
  Test: `test_ip_conflicts_are_refused`.

### Ready for real Cisco devices (EVE-NG): masks saved, and the lab's "door" is protected
- 🟡 `vendors/cisco_ios.py` (Infrastructure): "Find links & IPs" now reads `show ip interface` instead of
  `show ip interface brief`, so Cisco interfaces are saved WITH their mask (`Ethernet0/0 10.1.2.1/24`). The
  rollbacks that put an old IP back need it. Run "Find links & IPs" again on real devices to refresh them.
  Test: `test_cisco_interfaces_are_read_with_their_mask`.
- 🟢 `validation/validator.py`: a warning when a change (shutdown, new IP, no IP) hits the interface that connects
  this PC to the lab (its subnet holds this PC's IP, e.g. R2 e0/3 192.168.43.2/24 with the PC on 192.168.43.1):
  every device is reached through it. Test: `test_the_door_to_the_lab_warns`.

### Simple "set the IP" requests are written by the program, without the AI
- 🟢 `intent/translator.py`: "Set the IP of interface Ethernet0/1 on R1 to 10.0.12.0/31" (or "... to 10.5.5.1
  with mask 255.255.255.0") on a Cisco IOS or simulated device is turned into commands by the program itself:
  `interface Ethernet0/1` / `ip address 10.0.12.0 255.255.255.254`. Always right, instant, and the user's IP
  exactly (the small AI refused valid /31 addresses). Short names (`e0/1`) become the saved interface name, and
  the rollback puts the interface's old IP back when it's known. Other wordings and vendors go to the AI as
  before; the plan is validated like any other. The plan has a new field `"written_by": "program"`.
- 🟡 `pipeline.py` (shared file): no second try for a plan the program wrote (it would be the same).
  Test: `test_simple_ip_request_is_written_by_the_program`.

### When the AI refuses a request with valid IPs
- 🔴 Removed: the rules "keep the user's IP / the /31 rule" in the AI's instructions (`intent/translator.py`). The
  small local AI ignored them.
- 🟡 `pipeline.py` (shared file): if the request has IPs the program checked as valid and the AI made no plan,
  it's asked once more ("these IPs are valid, make the plan with them exactly as written"). If it still makes no
  plan, its reasons are hidden (they were wrong and suggested other IPs) and the message is ours: "The AI couldn't
  make a plan for this request. Your IP addresses (...) are valid. Nothing was changed." Requests without IPs
  (VLANs...) work as before. Test: `test_refused_valid_ip_gets_a_second_try_and_our_words`.

### A wrong IP in the request is refused in the program's own words
- 🟢 `validation/validator.py`: `request_problems()` checks the IPs the user typed (300.1.1.1, 10.5.5, a broken
  mask, or a network/broadcast address given to an interface). If one is wrong, the errors are only
  "Your request: ...", whatever the AI wrote. Network addresses in route/OSPF requests are fine.
- 🟡 `pipeline.py` (shared file): when the request itself is wrong, the AI is not asked a second time (it would
  only guess a new value, and it's slow on a local model), its plan is hidden, and the summary is ours:
  "This can't be done. 10.1.1.0/24 uses 10.1.1.0, the network address of 10.1.1.0/24...".
  Test: `test_wrong_ip_in_the_request_is_refused_in_our_words`.

### The AI says what's wrong, without suggesting another value
- 🟡 `pipeline.py` (shared file): the second-try rule now says to explain why the request can't be done and the
  rule it breaks, but NOT to suggest a replacement (it used to answer "the IP should be 10.1.1.1/24"). The user
  decides the new value.

### The AI may not change the user's IP addresses
- 🟢 `validation/validator.py`: every new IP address the user typed must appear in the plan's commands. The AI
  once turned "10.1.1.0/24" into `ip address 10.1.1.1` without saying so. Now that's an error, so the AI's second
  try must keep the IP (then the IP check says why it's wrong) or return no changes and explain. Masks and IPs
  the network already has are not checked.
  Test: `test_the_ai_may_not_change_the_users_values`.

### Validation refuses invalid IP addresses
- 🟢 `validation/validator.py`: `ip address` (and FortiGate `set ip`) must have a real IP (4 numbers 0-255), a
  real mask (`255.0.255.0` and the ACL wildcard `0.0.0.255` are refused), and not the network or broadcast address
  of its subnet (`10.1.1.0/24`, `10.1.1.255/24`). Masks can be `255.255.255.0`, `24` (Huawei) or `/24` (Arista).
  Test: `test_invalid_ip_address_is_refused`.

### Validation checks the rollback of a management-IP change
- 🟢 `validation/validator.py`: the AI once "undid" a new management IP with `no interface Vlan1` (that would
  leave the device with no way in). Now it's an error if a rollback deletes the management interface, or if a
  plan changes the management IP and the rollback doesn't put the old IP back. The error tells the AI the right
  rollback (`interface Vlan1` / `ip address 10.0.1.11 255.255.255.0`), so its second try can fix it.
  Test: `test_rollback_must_not_cut_the_device_off`.

### The program follows a device to its new management IP
- 🟢 `control/controller.py`: when an applied plan gives a device's management interface a new IP, the program
  saves the new IP (and the interface line, e.g. `Vlan1 10.0.1.50/24`) by itself. On a real device the SSH
  session drops at that moment: that is now expected, so the program pings the new IP; answers = success,
  silent = failure (rollback as usual). Nothing moves with `DRY_RUN=true`.
- 🟡 `validation/validator.py`: the management-IP helpers are now functions Control uses too
  (`management_interface`, `new_management_ip`); the warning text says the program will follow the new IP.
- If a LATER device in the same plan fails, the rollback puts the old IP back on the device, and the program
  follows it back to the old IP the same way (ping, then save).
  Tests: `test_new_management_ip_is_saved_automatically`, `test_dropped_connection_*`,
  `test_rollback_*_back_to_its_old_ip`, `test_dry_run_does_not_move_the_device`.

### Warning before cutting the program off from a device
- 🟢 `validation/validator.py`: the program reaches each device on its management IP. If that IP is on one of the
  device's known interfaces (e.g. `Vlan1 10.0.1.11/24`), a `shutdown`, `no ip address` or a new `ip address` on
  that interface now gets a warning: the program (and the rollback) would lose the device. Only a warning, the
  user may really want it. Test: `test_change_on_the_management_interface_warns`.
- 🟡 Same check: an IP typed with spaces around it (`"   10.0.1.11"`) is still recognized.

### The AI no longer guesses when the request itself is wrong
- 🟡 `pipeline.py` (shared file): when a plan is rejected, the second try now tells the AI to fix only its own
  mistakes. If the user's request is impossible (e.g. VLANs 20-5000), it must return no changes and explain the
  allowed values, instead of quietly changing them (it used to turn 5000 into 500). Test:
  `test_ai_is_told_not_to_guess_the_users_values`.

### Validation refuses invalid VLAN numbers
- 🟢 `validation/validator.py`: a `vlan N` (also `switchport access vlan N`, FortiGate `set vlanid N`) with N
  outside 1-4094 is an error, so a plan like "Create VLAN 5000" is blocked before it reaches a device.
  Test: `test_invalid_vlan_number_is_refused`.
- 🟡 The VLAN check also reads lists: `switchport trunk allowed vlan add 4095`, `allowed vlan 10,20-5000`,
  Huawei `vlan batch 10 to 20`, and sub-interfaces `encapsulation dot1Q 5000`.

### Type a device's interfaces by hand
- 🟢 Tools > Add / edit a device: an "Interfaces" box (one per line, e.g. `e0/0 192.168.1.1/24`), for devices
  Find links can't read (simulated or hand-drawn labs). The AI needs them to plan routing. Short names become
  full ones (`e0/0` -> `Ethernet0/0`); Edit fills the box with the saved interfaces. Files: `index.html`, `web.py`.

### Version badge
- 🟢 `index.html`: a small "v1.1" badge next to the logo (shows which version you are running).

### More room for the important parts of the page
- 🟡 `index.html` only: the big number cards are now small counters on one line under "Network Overview"
  (Down turns red). Availability, Network health and Devices by vendor moved into a panel that opens with
  the "Charts" button (top right or left bar) and closes with a click outside or Esc. The topology gets the space.

### Lab configs match the new topology
- 🟡 `lab/VPN_lab_config_with_management.txt` (notes, not code): management through R2 e0/3
  (192.168.43.2, host-only cloud); devices are managed on their loopbacks (R1/R2/R3 = 10.0.0.1/2/3)
  and the switches on Vlan1 (SW1 10.0.1.11, SW3 10.0.3.13); R2 sends a default route into OSPF.

### New look for the web page (charcoal + green monitoring theme)
- 🟡 `index.html` only: new colors, a left icon bar (Intent, Topology, Devices, Tools, Results),
  a header with a green/red status arrow and vendor chips, the device search moved to the top bar,
  big-number cards with an **Availability** gauge (devices up out of those checked), thicker rings.
  Every button, URL and rule works as before; still one screen, no scrolling.

### A device's own username is hidden too
- 🟡 Like the password, a device's saved username is never sent to the page (`has_username` tells
  it one exists). Edit shows ●●●●●● in the username box. Rules unchanged: leave the dots = keep it,
  empty the box = use the `.env` username, type a new one = replace it.
- Files: `ibn/interface/web.py`, `index.html`, `tests/test_ibn.py`.

### Loading spinners + nicer "saved" message
- 🟡 `ibn/interface/templates/index.html`: buttons that wait for the server (Make a plan, Approve,
  Scan, Find links, Refresh up/down, Path, What-if, Critical devices, Save device, Link, Start a new
  topology) show a small spinning circle and can't be clicked twice while working. The plan box
  shows "The AI is writing the plan..." with a spinner.
- 🟡 "Saved" and "linked" messages now show a white check mark in a green circle.

### Refresh up/down: no false "down" after a device comes back
- 🟡 `ibn/infrastructure/discovery.py`: sends 2 pings instead of 1 (the first one is often
  dropped while the router re-learns the device's MAC address).
- 🟡 Fix of the first version of this change: it looked for the text `TTL=` in ping's answer,
  which Windows in some languages doesn't print, so every device showed "down". Now: ping
  succeeded + `TTL=` → up; ping succeeded without `TTL=` → up only if the SSH/Telnet port answers
  (this still filters out Windows' "Destination host unreachable").
- `tests/test_ibn.py`: 1 new test.

### Manual links: names are matched, errors are shown
- 🟡 **Link two devices** now ignores CAPITALS and extra spaces (`r1 ` = `R1`). Before, a link
  with a slightly different name was saved but never drawn, with no error.
- 🟡 A name that doesn't exist (or the same device twice) shows an error in Results.
- 🟡 Old broken links (to names that don't exist) are no longer sent to the page.
- Files: `ibn/interface/web.py`, `index.html`, `tests/test_ibn.py` (1 new test).

### Change only a device's password
- 🟡 Edit a device → type only a new password → Save: the password changes and the username
  stays (its own, or the `.env` one). Before, a device using the `.env` username lost the new
  password. Emptying both boxes still goes back to the full `.env` login.
- 🟡 The page only learns *whether* a password is saved (`has_password`, used for the hint in the
  password box), never the password. (The login is not shown in the device table.)
- Files: `ibn/interface/web.py`, `index.html`, `tests/test_ibn.py` (1 new test).

### Device login fix + faster adding
- 🟡 Editing a device and **emptying the username** now really removes its own login, so it
  uses the one in `.env` again (before, the old username stayed). An empty password alone
  still keeps the saved password. Name and IP are now required.
- 🟡 **Save device / Link** show a green ✓ next to the button and clear the form for the next one;
  you stay in Tools. Only an error opens the Results tab.
- Files: `ibn/interface/web.py`, `index.html`, `ibn/knowledge/file_graph.py` (a field set to
  None is removed), `ibn/knowledge/base.py` (docstring), `tests/test_ibn.py` (3 new tests).

### Dashboard fits on one screen
- 🟡 `ibn/interface/templates/index.html`: everything fits in the window, no page scrolling
  (long lists scroll inside their own box). Right side has tabs: **Devices | Tools | Results**;
  Results opens by itself when there's something new to show. Ring charts are now a full
  circle at 100%. Small screens (under 1100 px) still get a normal scrolling page.

### Dark "network monitor" dashboard
- 🟡 `ibn/interface/templates/index.html`: new dark design. Top navigation bar; tiles for
  routers / switches / firewalls / other devices / links / down; **Network health** and
  **Devices by vendor** ring charts; larger topology; **Device inventory** table with a search box.
  The device type is guessed from the vendor and name (only for display).
- Only real data is shown (no traffic graphs: the project doesn't collect traffic yet).
- No other file changed: every button calls the same API URLs as before.

### Old topology data no longer sticks around
- 🟢 **Start a new topology** button (Discovery card): deletes every device, link and history
  entry, safely, while the program runs. New URL `POST /api/reset`.
- 🟡 **Find links** now also **removes** links that are gone: only when both devices answered and
  neither reports the other. Links added by hand ("Link two devices") are never removed.
- 🟡 Deleting a device (**X**) now also deletes its history, so a new device with the same name
  starts clean.
- Files: `ibn/knowledge/base.py` (new `clear()`, `add_link(..., manual=False)`; links now also
  have a `manual` field), `file_graph.py`, `neo4j_graph.py`, `ibn/infrastructure/discovery.py`,
  `ibn/interface/web.py`, `index.html`, `tests/test_ibn.py` (5 new tests), `docs/PROJECT_GUIDE.md`.
- Nothing was renamed or removed: other layers keep working as before.

### Dashboard look + Arabic text fixed
- 🟡 `ibn/interface/templates/index.html`: new dashboard layout. Status tiles at the top
  (devices, up, down, links, vendors), then 3 columns: request + plan | topology + results |
  devices + tools. "Add device" and "Link two devices" fold away; device states are colored labels.
- 🟡 Same file: Arabic mixed with English now shows in the right order (each text picks its
  own direction automatically).
- No other file changed: every button calls the same API URLs as before.

### Clearer driver name + prompts for the team
- 🟡 `ibn/infrastructure/drivers/netmiko_cli.py` → renamed to **`cli.py`**, class `NetmikoDriver`
  → **`CliDriver`** ("devices you control by typing commands, over SSH or Telnet").
  Updated where it's used: `drivers/__init__.py`, `tests/test_ibn.py`, `README.md`,
  `docs/PROJECT_GUIDE.md`. Nothing else changed.
- 🟡 `docs/TEAM_GUIDE.md`: ready-to-copy **prompts for Claude** (section 10), and device fields
  added to the contracts (section 6).
- 🟡 `CLAUDE.md`: device fields are a contract too; "add, don't rename".

### Team setup: Claude does the editing
- 🟡 `docs/TEAM_GUIDE.md` + `CLAUDE.md`: the daily workflow is now "ask Claude → Claude edits,
  tests, pushes to your branch → you run `update.bat` + `start.bat`". Hand edits only rarely.

### Team setup
- 🟢 **`docs/TEAM_GUIDE.md`**: how the 4 of us work together (setup, branches, Pull Requests,
  layer owners, contracts, conflicts, AI options, ideas per layer, PR checklist).
- 🟢 **`CLAUDE.md`**: team rules that Claude Code reads automatically in every session.
- 🟢 **`.github/workflows/tests.yml`**: GitHub runs the tests on every push and Pull Request.
- 🟡 `README.md`: link to the team guide.
- Branches on GitHub: `main` (official version) + `ebraam`, `asmaa`, `menna`, `heba`.

### Readable device history
- 🟡 `ibn/interface/templates/index.html`: the **History** button shows one card per change
  (newest first: ✅/❌/🔍, time, your request, commands) instead of raw JSON.
  The device output is folded under "Show device output". Nothing else changed.

### Topology view remembers zoom and position
- 🟡 `ibn/interface/templates/index.html`: zoom and view position saved in the browser;
  new **Center view** button.

### Keep the topology layout + remove a link
- 🟡 `ibn/interface/templates/index.html`: the picture is updated instead of redrawn
  (box positions remembered); click a line → **Remove link** button.
- 🟡 `ibn/knowledge/base.py`, `file_graph.py`, `neo4j_graph.py`: new function `delete_link(a, b)`.
- 🟡 `ibn/interface/web.py`: new URL `DELETE /api/links`.

### Find links shows a readable result
- 🟡 `ibn/interface/web.py` + `index.html`: "Done: 4 links in the graph…" instead of `{"errors": []}`.

### Graph questions (NetworkX)
- 🟢 **`ibn/knowledge/graph_analysis.py`** (new file, 55 lines): path, backup paths,
  "what if a device goes down", critical devices.
- 🟡 `ibn/interface/web.py`: 3 new URLs under `/api/graph/...`.
- 🟡 `ibn/interface/templates/index.html`: new **"Ask the network graph"** box.
- 🟡 `ibn/validation/validator.py`: new check 8 (warning for risky changes on critical devices).
- 🟡 `ibn/intent/translator.py` + `ibn/pipeline.py`: the AI now also receives the links.
- 🟡 `requirements.txt`: added `networkx` (installed automatically).
- 🟡 `ibn/knowledge/__init__.py`: one import line.

### update.bat / start.bat
- 🟡 `update.bat`: quiet; only reinstalls libraries when `requirements.txt` changed;
  runs from a temporary copy (fixes the `'q' is not recognized` error).
- 🟡 `start.bat`: quiet first-time install.

### Removed the web-page router feature (home routers)
- 🔴 `ibn/infrastructure/drivers/web_gui.py` (deleted, 340 lines)
- 🔴 `tests/test_web_gui.py`, `tests/fake_router.py`, `tests/__init__.py` (deleted)
- 🟡 `drivers/__init__.py`, `settings.py`, `rules.py`, `validator.py`, `translator.py`,
  `index.html`, `requirements.txt`, `.env.example`, `start.bat`, `update.bat`:
  removed everything belonging to it (`playwright`, `SHOW_BROWSER`, URL field…).

---

## Before the project guide (summary)
- First version: 5 layers, knowledge base (JSON file / Neo4j), web page, Cisco SSH driver, tests.
- SSH fix for older Cisco IOS (`paramiko<4`), `start.bat` / `update.bat`, EVE-NG lab config.
- Check steps (`ping`/`show`), interface IPs for the AI, interface-name validation,
  automatic AI retry, safer delete button, "Failed" for failed checks.
