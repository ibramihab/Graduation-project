# Testing the AI automatically

```
python evaluation\run_tests.py                  every test, RAG off then on
python evaluation\run_tests.py --rag on         only with RAG
python evaluation\run_tests.py --only dhcp trunk
python evaluation\run_tests.py --quick --rag off   only the 15 quick tests, without RAG
python evaluation\run_tests.py --level 1 --rag off only the 5 quick tests of level 1
```

`--quick` runs the 15 tests marked `"quick": true` in `tests.json`: every topic (routes, OSPF, ACL, VLAN,
trunk, DHCP, interface, check, refusal, 2 in Arabic), so a slow laptop gets a result in a few minutes.

The 15 quick tests are split into 3 levels of 5 (`"level"` in `tests.json`), each harder than the last; the
results show a score per level (on screen and in a "By level" table of the HTML report):

| Level | What it tests | Tests |
|---|---|---|
| 1 | simple: one device, everything given | route-1, interface-ip, trunk, check-routes, refuse-reload |
| 2 | harder: several steps, a protocol, Arabic, a reachability check | route-arabic, ospf-link, vlan-port, dhcp, check-ping |
| 3 | scenarios: several devices, a goal instead of commands, a vague request | route-both-ways, ospf-three-routers, acl-block, acl-arabic, refuse-vague |

- Uses your AI settings from `.env` (`LLM_PROVIDER`, `OLLAMA_MODEL`...). Ollama must be running.
- Uses the fixed test network in `lab.json`, NOT your devices, and sends nothing to any device.
- Each plan gets a mark:
  - **PASS**: every required command is there, nothing forbidden, validation OK, rollback present
  - **HALF**: right commands, smaller problem (validation errors, no rollback...)
  - **FAIL**: required commands missing, forbidden command, no plan, or an error
- Results: printed, and saved in `data\evaluation\<date>_<model>.html`: **open it in the browser** (colored table,
  RAG off vs on side by side, every plan). The same data is in a `.csv` next to it.

## Adding a test
Add an item to `tests.json`:
```json
{"id": "route-1", "feature": "static route",
 "request": "on R2 add a static route to 172.31.3.0/24 via R1",
 "kind": "config",                       // config, check (show/ping only) or refuse (no plan wanted)
 "must": {"R2": ["ip route 172.31.3.0 255.255.255.0 10.1.12.1"]},   // "*" = on any device
 "must_not": ["255.255.255.0 area"]}     // optional
```
Use the device names of `lab.json`, and keep tests DIFFERENT from the RAG examples
(the examples in `ibn/vendors/<vendor>/docs/`), or the AI just copies an example and the score lies.

Also: every plan made on the web page is saved in `data\plans.html` (open in the browser) and `data\plans.csv`
(setting `PLAN_LOG`).
