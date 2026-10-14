# What changed (newest first)

Every change to the project is listed here, so nothing surprises you.
**Type:** 🟢 new · 🟡 changed · 🔴 removed. Files under `docs/` and `README.md` are just text.

---

## Changes after the project guide was written

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
