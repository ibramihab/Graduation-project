# What changed (newest first)

Every change to the project is listed here, so nothing surprises you.
**Type:** 🟢 new · 🟡 changed · 🔴 removed. Files under `docs/` and `README.md` are just text.

---

## Changes after the project guide was written

### Optional port per device (for PAT / port forwarding)
- 🟡 `ibn/infrastructure/drivers/netmiko_cli.py`: connects to the device's `port` if set
  (empty = normal 22/23).
- 🟡 `ibn/interface/web.py` + `index.html`: new **Port** box in "Add / edit a device";
  the device table shows `ip:port`.
- 🟡 `tests/test_ibn.py`: 1 new test. `README.md`, `docs/PROJECT_GUIDE.md`: one line each.

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
