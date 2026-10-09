# Simple IBN: the complete project guide

This guide explains **how the project works**, **what every file does**, **which files
you can remove**, and **how to grow it** into a bigger project.
Read it top to bottom once; afterwards use it as a map.

---

## Part 1: The big picture

### 1.1 What the system does, in one sentence

You type what you want in English, an AI turns it into device commands, the
system checks they are safe, you approve, and the system logs in to the devices,
applies the commands, and undoes everything if something fails.

### 1.2 The 5 layers + 1 shared memory

The project follows your design diagram exactly. **Each layer is one folder** inside `ibn/`:

```
  YOU (browser)
     │
     ▼
 ┌──────────────────────┐
 │ 1. Interface layer    │  ibn/interface/      the web page + web server
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │ 2. Intent layer       │  ibn/intent/         the AI: English → plan        ┐
 └──────────┬───────────┘                                                    │
            ▼                                                                │  all layers read/write
 ┌──────────────────────┐                                                    │  the Knowledge base:
 │ 3. Validation layer   │  ibn/validation/     safety checks on the plan     ├─ ibn/knowledge/
 └──────────┬───────────┘                                                    │  (devices, links, state,
            ▼   (you click Approve)                                          │   backups, history)
 ┌──────────────────────┐                                                    │
 │ 4. Control layer      │  ibn/control/        apply + rollback + history    │
 └──────────┬───────────┘                                                    │
            ▼                                                                │
 ┌──────────────────────┐                                                    │
 │ 5. Infrastructure     │  ibn/infrastructure/ drivers that talk to devices ┘
 └──────────────────────┘   (SSH/Telnet) + discovery (ping, CDP)
            │
            ▼
   real devices (EVE-NG routers and switches)
```

`ibn/pipeline.py` is the **glue**: it calls the layers in the right order.

### 1.3 The journey of one request (follow this once and you understand everything)

Example: you type **"Create VLAN 10 named HR on SW1"** and click **Make a plan**.

| # | What happens | File |
|---|---|---|
| 1 | The page sends your text to the server (`POST /api/intent`). | `interface/templates/index.html` → `interface/web.py` |
| 2 | The server calls `pipeline.propose(text)`. | `pipeline.py` |
| 3 | The translator builds the AI's instructions: rules + examples + **your device list from the knowledge base** (names, vendor, interface IPs, never passwords). | `intent/translator.py`, `knowledge/` |
| 4 | The AI (Claude or Ollama) answers with a **plan** in a fixed JSON shape (see 1.4). | `intent/llm.py` |
| 5 | Validation checks the plan: device exists? vendor supported? device up? dangerous commands? real interface names? | `validation/validator.py`, `validation/rules.py` |
| 6 | If validation found errors, the errors are sent back to the AI for **one more try**. | `pipeline.py` |
| 7 | The plan (commands, rollback, errors, warnings) is shown on the page. | `index.html` |
| 8 | You click **Approve & apply** (`POST /api/approve/<id>`). The plan is **validated again** (the network may have changed). | `web.py`, `pipeline.py` |
| 9 | Control: for each step, pick the right **driver** for the device's vendor, log in, save a **config backup**, send the commands. | `control/controller.py`, `infrastructure/drivers/` |
| 10 | If any device fails → run the **rollback** commands on every device already changed. | `control/controller.py` |
| 11 | Everything is written to the device's **history** in the knowledge base. The page shows the result. | `knowledge/`, `index.html` |

### 1.4 The "plan": the one data shape every layer understands

```json
{
  "summary": "Create VLAN 10 named HR on SW1",
  "changes": [
    { "device": "SW1",
      "type": "config",                       // "config" = changes the device
      "commands": ["vlan 10", "name HR"],     //            (config mode)
      "rollback": ["no vlan 10"] },           // how to undo it
    { "device": "SW1",
      "type": "check",                        // "check" = read-only (ping, show)
      "commands": ["show vlan brief"],
      "rollback": [] }
  ]
}
```

The AI **produces** it, validation **checks** it, control **executes** it.
Because all layers agree on this shape, you can replace any layer without touching the others.

---

## Part 2: The folder map

When you open the project in VS Code, you see this. Tags:
**[CORE]** = the system needs it · **[OPTIONAL]** = a feature you could remove ·
**[SUPPORT]** = helps you work, not part of the running system ·
**[AUTO]** = created automatically by tools, never edit it, ignore it.

```
Graduation-project/
│
├── run.py                         [CORE]     starts the program
├── start.bat                      [SUPPORT]  double-click: install (first time) + start
├── update.bat                     [SUPPORT]  double-click: download newest version from GitHub
├── requirements.txt               [CORE]     list of Python libraries the project needs
├── .env                           [CORE]     YOUR settings + secrets (not on GitHub)
├── .env.example                   [SUPPORT]  template for .env
├── docker-compose.yml             [OPTIONAL] starts the Neo4j graph database
├── README.md                      [SUPPORT]  short user manual
├── docs/PROJECT_GUIDE.md          [SUPPORT]  this guide
├── lab/VPN_lab_config_...txt      [SUPPORT]  the Cisco configs for your EVE-NG lab (notes, not code)
├── .gitignore                     [SUPPORT]  tells Git which files never to upload
├── .gitattributes                 [SUPPORT]  keeps .bat files in Windows format
├── .vscode/settings.json          [SUPPORT]  hides the [AUTO] folders in VS Code
│
├── ibn/                           ← ALL the program's code ("ibn" = intent-based networking)
│   ├── __init__.py                [CORE]     marks the folder as a Python package
│   ├── settings.py                [CORE]     reads .env → settings used everywhere
│   ├── pipeline.py                [CORE]     the glue: runs the layers in order
│   │
│   ├── interface/                 LAYER 1
│   │   ├── web.py                 [CORE]     web server: one function per button
│   │   ├── templates/index.html   [CORE]     the web page (HTML + CSS + JavaScript)
│   │   └── static/vis-network.min.js [CORE]  library that draws the topology graph (don't edit)
│   │
│   ├── intent/                    LAYER 2
│   │   ├── llm.py                 [CORE]     talks to the AI (Claude or Ollama)
│   │   └── translator.py          [CORE]     instructions + examples for the AI, the plan shape
│   │
│   ├── validation/                LAYER 3
│   │   ├── validator.py           [CORE]     the safety checks
│   │   └── rules.py               [CORE]     lists of dangerous / warning commands per vendor
│   │
│   ├── control/                   LAYER 4
│   │   └── controller.py          [CORE]     apply, rollback, check steps, history
│   │
│   ├── infrastructure/            LAYER 5
│   │   ├── discovery.py           [OPTIONAL] ping scan, up/down, CDP links, interface IPs
│   │   └── drivers/
│   │       ├── __init__.py        [CORE]     the vendor → driver list
│   │       ├── base.py            [CORE]     the rules every driver must follow
│   │       ├── netmiko_cli.py     [CORE]     SSH/Telnet devices (Cisco, Arista, Huawei...)
│   │       └── simulated.py       [OPTIONAL] fake device for practice and tests
│   │
│   └── knowledge/                 SHARED COMPONENT
│       ├── __init__.py            [CORE]     picks file or Neo4j storage
│       ├── base.py                [CORE]     the rules every storage must follow
│       ├── file_graph.py          [CORE*]    graph stored in data/knowledge.json
│       └── neo4j_graph.py         [CORE*]    graph stored in Neo4j        (*you need one of the two)
│
├── tests/                         [SUPPORT]  automatic tests (run: pytest)
│   └── test_ibn.py                           tests for the whole pipeline
│
├── data/                          [AUTO] your devices + history (knowledge.json). Not on GitHub.
├── venv/                          [AUTO] the installed libraries (thousands of files!). Ignore.
├── __pycache__/ (many places)     [AUTO] Python's compiled copies of the files. Ignore.
└── .pytest_cache/                 [AUTO] created when tests run. Ignore.
```

**Why VS Code looked overwhelming:** `venv/` alone contains thousands of files
(Flask, Netmiko, Neo4j... all their code). None of it is yours. The real
project is about **25 small files, ~1,450 lines** in total. The new
`.vscode/settings.json` hides the [AUTO] folders so you only see your code.

---

## Part 3: Every file explained

For each file: **what it does**, **why it exists**, **can it be removed?**

### Root files

**`run.py`** (7 lines). Starts the web server on http://localhost:5000.
Why: Python needs one "start here" file. *Needed.*

**`start.bat` / `update.bat`** (Windows only). Double-click helpers. `start.bat` creates
the `venv`, installs libraries (first time only), then runs `run.py`.
`update.bat` runs `git pull` and installs any new libraries.
*Not needed by the program*: you could type the commands yourself. Kept because they save time.

**`requirements.txt`**. The shopping list of libraries. `pip install -r requirements.txt` installs them:

| Library | Used by | Needed? |
|---|---|---|
| `flask` | web server (interface) | yes |
| `anthropic` | Claude AI (`llm.py`) | only if you use Claude |
| `requests` | Ollama AI (`llm.py`) | only if you use Ollama |
| `neo4j` | Neo4j storage | only if `KB_BACKEND=neo4j` |
| `netmiko` | SSH/Telnet to devices | yes (for real devices) |
| `paramiko<4` | SSH library under Netmiko; pinned because version 4+ can't talk to older Cisco IOS | yes |
| `python-dotenv` | reads `.env` | yes |
| `pytest` | runs tests | only for testing |

**`.env`** (your copy) / **`.env.example`** (template). All settings in one place: which
AI, which storage, device login, `DRY_RUN`. Why a separate file: secrets
(API keys, passwords) must never be uploaded to GitHub, and `.gitignore` protects `.env`.

**`docker-compose.yml`**. One command (`docker compose up -d`) starts the Neo4j database.
*Remove it* if you only use `KB_BACKEND=file`.

**`.gitignore`**. Tells Git never to upload `.env`, `data/`, `venv/`, caches. *Needed* (protects secrets).

**`.gitattributes`**. Makes sure `.bat` files keep Windows line endings (otherwise Windows can't run them). Tiny, keep it.

**`README.md`**. Short manual (how to install/run). **`docs/PROJECT_GUIDE.md`**: this guide.

**`lab/VPN_lab_config_with_management.txt`**. The configs you paste into the EVE-NG devices
(your lab + management IPs + SSH). Notes for humans; the program never reads it.

### `ibn/`: the program

**`ibn/__init__.py`** (and every other `__init__.py`). Python needs a file called
`__init__.py` in a folder to treat it as a "package" (a folder you can import from).
Some of them also make imports shorter: e.g. `intent/__init__.py` lets other files write
`from ibn.intent import translate` instead of `from ibn.intent.translator import translate`.
*Needed; don't delete them.*

**`ibn/settings.py`** (37 lines). Reads `.env` once and turns it into Python variables
(`settings.LLM_PROVIDER`, `settings.DRY_RUN`...). Every other file reads settings from here.
Why: one place for all settings, with sensible defaults if something is missing.

**`ibn/pipeline.py`** (46 lines): the glue. Two functions:
- `propose(text)` = intent → validation (+ one automatic retry if validation fails). Stores the
  plan in `PENDING` (a dictionary in memory) and returns it to the page.
- `approve(plan_id)` = takes the plan from `PENDING`, validates it **again**, then calls the control layer.

Why separate from `web.py`: the web page is just one possible interface. A chat bot, a
command-line tool or a mobile app could call the same two functions.

### Layer 1: Interface (`ibn/interface/`)

**`web.py`** (77 lines). The web server (Flask). Each URL is one function = one button:

| URL | Button | Does |
|---|---|---|
| `GET /` | (opening the page) | sends `index.html` |
| `POST /api/intent` | Make a plan | `pipeline.propose` |
| `POST /api/approve/<id>` | Approve & apply | `pipeline.approve` |
| `GET /api/topology` | (page load) | devices + links for the table and graph (passwords removed) |
| `POST /api/devices` | Save device | add or update a device |
| `DELETE /api/devices/<name>` | X | delete a device |
| `POST /api/links` | Link | add a link between two devices |
| `GET /api/devices/<name>/history` | History | the device's change history |
| `POST /api/discover` | Scan (ping) | ping-scan a subnet |
| `POST /api/discover-links` | Find links & IPs | CDP neighbors + interface IPs |
| `POST /api/refresh` | Refresh up/down | ping every device |

This list is called an **API**. Because the page talks to the server only through it,
you can build a completely new page (React, mobile app) without changing Python code.

**`templates/index.html`** (191 lines). The whole web page: HTML (the boxes and
buttons), CSS (colors and layout, at the top), JavaScript (at the bottom: what happens
when you click). Plain JavaScript, no framework, so it's easy to read.

**`static/vis-network.min.js`**. A ready-made library that draws the topology graph.
It's minified (squeezed into one unreadable line). **Never edit it.** It's stored inside
the project so the page works in a lab without internet.

### Layer 2: Intent (`ibn/intent/`)

**`llm.py`** (66 lines). Talks to the AI. Every AI class has **one method**:
`ask_json(system, user, schema) → dict` = "here are your instructions, here is the
request, answer in exactly this JSON shape".
- `ClaudeLLM`: cloud AI with an API key (Anthropic SDK). Asks for JSON matching the
  schema, and if the model declines it retries on a fallback model.
- `OllamaLLM`: local AI on your PC. `temperature 0` (no randomness) and `num_ctx 8192`
  (Ollama's default 2048 tokens silently cuts long instructions).
- `get_llm()`: picks one based on `LLM_PROVIDER` in `.env`.

**`translator.py`** (136 lines). The "brain instructions":
- `PLAN_SCHEMA`: the exact JSON shape of a plan (Part 1.4).
- `SYSTEM_PROMPT`: rules for the AI (config vs check steps, use real interface names,
  Cisco interface sub-mode, how to block traffic with ACLs)
  + **worked examples** (small models learn a lot from examples).
- `translate()`: inserts your device list (with interface IPs, without passwords), asks
  the AI, then cleans the answer (removes `configure terminal`/`end`, which the driver adds itself).

👉 **This is the file to edit to make the AI smarter** (better rules, more examples).

### Layer 3: Validation (`ibn/validation/`)

**`validator.py`** (96 lines). `validate(plan) → {"ok", "errors", "warnings"}`. Checks:
1. the device exists in the knowledge base
2. there is a driver for its vendor
3. the device isn't "down"
4. there are commands (and a rollback, else a warning)
5. no **blocked** commands (from `rules.py`), even inside the rollback
6. `check` steps contain only read-only commands; `config` steps don't contain `ping`/`show`
7. physical interface names (`Ethernet0/0`, `Gi0/1`...) really exist on that device

Errors **block** the plan (no Approve button). Warnings are shown, you decide.

**`rules.py`** (41 lines). Just **lists**, no logic: `BLOCKED` (per vendor),
`WARN`, `CHECK_ALLOWED`. 👉 To add a safety rule you only add one line here.

### Layer 4: Control (`ibn/control/`)

**`controller.py`** (91 lines). `apply_plan(plan)`:
- `config` step: get the device's driver → log in → save config backup → send commands.
- `check` step: run read-only commands, show the output.
- If a `config` step fails → `_rollback()` runs the undo commands on every device
  already changed (newest first), plus the one that failed.
- `_record()` writes the history for every device.
- `DRY_RUN=true` → shows what would be sent, sends nothing.

### Layer 5: Infrastructure (`ibn/infrastructure/`)

**`drivers/base.py`** (50 lines): **the contract**. Every driver must have:
`connect`, `disconnect`, `get_config` (backup), `send_config` (apply). Optional:
`run_commands` (check steps), `get_interfaces`, `get_neighbors`.
The control layer only calls these names, so it never needs to know if it's talking
to Cisco over SSH, a simulated device, or (in the future) an SDN controller.

**`drivers/__init__.py`** (26 lines): **the registry**. A dictionary
`vendor name → driver class`. `get_driver(device)` looks up the device's vendor here.
👉 Adding a vendor = one line here.

**`drivers/netmiko_cli.py`** (83 lines): every CLI device, via the Netmiko library
(which knows 100+ vendors). `NETMIKO_TYPES` = our vendor name → (Netmiko type,
"show config" command, "show interfaces" command). SSH or Telnet (`protocol` field).
Detects device errors (`% Invalid input`...) so a rejected command raises an error → rollback.

**`drivers/simulated.py`** (28 lines): a fake device in memory. A command containing
"invalid" fails (to demo rollback). *Optional*, but the tests use it and it's great for demos.

**`discovery.py`** (91 lines). `scan_subnet` (ping every address, 64 at a time),
`discover` (add answering IPs as devices), `refresh_states` (up/down), `discover_links`
(log in, save interface IPs, read CDP neighbors → links). *Optional*: you can add devices
and links by hand, but the AI needs the interface IPs it collects.

### Shared: Knowledge base (`ibn/knowledge/`)

**`base.py`** (57 lines): **the contract** for storage: `add_device`, `get_device`,
`list_devices`, `update_device`, `delete_device`, `add_link`, `list_links`,
`record_change`, `get_history` (+ helpers `find_by_ip`, `save_backup`).

**`file_graph.py`** (72 lines): the graph stored in one JSON file (`data/knowledge.json`):
`{"devices": {...}, "links": [["R1","R2"]], "changes": {...}}`. No install needed.

**`neo4j_graph.py`** (63 lines): the same methods using the Neo4j graph database
(Cypher queries like `MERGE (a)-[:CONNECTED_TO]-(b)`). Devices are nodes,
links are `CONNECTED_TO` relationships, history is `(Device)-[:HAS_CHANGE]->(Change)`.

**`__init__.py`**: `get_knowledge_base()` picks one of the two from `KB_BACKEND` in `.env`.

### Tests (`tests/`)

**`test_ibn.py`**: 13 tests of the whole flow using a fake AI and simulated devices
(validation blocks dangerous commands, rollback works, check steps are read-only, the
AI retries after errors...). Each test runs twice: with file storage and (if
`TEST_NEO4J=1`) with Neo4j.
Run all tests: `venv\Scripts\python -m pytest`. **Run them after every change.** If they
pass, you didn't break anything. *Not needed to run the program*, but they are your safety net.

---

## Part 4: What can be removed to make it simpler?

The **minimal core** (what the system can't run without) is:

```
run.py, requirements.txt, .env, ibn/settings.py, ibn/pipeline.py,
interface/ (web.py, index.html, vis-network.min.js), intent/ (llm.py, translator.py),
validation/ (validator.py, rules.py), control/controller.py,
drivers/ (__init__.py, base.py, netmiko_cli.py), knowledge/ (base.py + ONE of the two storages)
```

| You could remove | Saves | You lose |
|---|---|---|
| `neo4j_graph.py` + `docker-compose.yml` + `neo4j` library | ~80 lines + Docker | the "real graph database" (your original requirement) |
| `file_graph.py` | ~70 lines | running without Docker; the tests use it |
| `discovery.py` + 3 buttons | ~90 lines | ping scan, up/down, auto links, **interface IPs for the AI** |
| `simulated.py` | ~30 lines | practising without devices; the tests use it |
| `start.bat`, `update.bat`, `lab/`, `docs/` | nothing in the program | convenience and notes |

**Recommendation: don't remove anything more.** Each piece is small, separate and optional
at runtime. If a feature isn't configured, its code simply never runs. (The home-router
browser agent, `web_gui.py`, was already removed: it was the biggest piece and the local
AI was too slow for it. Its idea is described in Part 6 if you want it back later.)

---

## Part 5: Is this a prototype we can build on?

**Yes.** This is a working prototype (also called an MVP, "minimum viable product"):
small, but every layer of your design exists and works end to end on real Cisco
devices in EVE-NG.

### Why it can grow (the 4 "contracts")

The project is scalable because layers talk only through **4 fixed contracts**.
Behind a contract you can change anything:

| Contract | Defined in | Means you can... |
|---|---|---|
| **The plan** (JSON shape) | `translator.py` `PLAN_SCHEMA` | change the AI, the checks, or the executor independently |
| **`ask_json()`** | `llm.py` | swap/add any AI (Claude, Ollama, GPT, a fine-tuned model) |
| **`Driver`** | `drivers/base.py` | add any vendor or access method (SSH, web, REST, NETCONF, SDN) |
| **`KnowledgeBase`** | `knowledge/base.py` | swap storage (JSON, Neo4j, another DB) |

**Can existing files be modified, or do they serve only one task?** Every file can be
modified and extended. The rule is simple:
- Changing **what's inside** a function → safe, nothing else needs to change.
- Changing a **contract** (a function name, its inputs, or the plan shape) → also update
  the few places that call it. VS Code: right-click the name → "Find All References".
- After any change → run `pytest`.

### Honest limits of the prototype (what a "real product" would add)

| Limit now | Upgrade later |
|---|---|
| No login on the web page | user accounts + roles (admin / viewer) |
| One shared device password in `.env`, passwords stored as plain text | encrypted secrets store (e.g. HashiCorp Vault) |
| Pending plans live in memory (lost on restart) | store plans in the knowledge base |
| One task at a time; long tasks keep the page waiting | background jobs + progress updates on the page |
| Small local AI is slow and makes mistakes | Claude API or a bigger/fine-tuned local model + an accuracy test set |
| Validation = rules only | lab simulation before applying (Batfish), check after applying |
| You must click "Find links & IPs" | automatic discovery every few minutes (closed loop) |
| Config changes not saved on devices (`write memory`) | optional save step after success |
| No support for home routers that only have a web page | a browser-agent driver (Part 6) with Claude API |

---

## Part 6: How to upgrade each layer (where to edit)

### Add a vendor
1. If Netmiko supports it: one line in `NETMIKO_TYPES` (`drivers/netmiko_cli.py`).
2. One line in `DRIVERS` (`drivers/__init__.py`) if it needs a new driver class.
3. Add it to the vendor drop-down (`index.html`).
4. Optional: its dangerous commands in `rules.py`, and an example in `translator.py`.

### Add a new access method (REST API, NETCONF, SNMP) or SDN
Create `drivers/restconf.py` with `class RestconfDriver(Driver)` and the 4 methods,
then one line in `DRIVERS`. For SDN: `OnosDriver.send_config()` calls the controller's
REST API instead of a device. The other layers don't change.

### Add home routers that only have a web page (idea that was tried and removed)
Write `drivers/web_gui.py` with a `WebGuiDriver(Driver)` that opens the router page in a
real browser (Playwright library), logs in, then lets the AI pick the next click/fill
until the task is done. It worked on a fake router but was too slow with a local 7B
model; with the Claude API it would be fast. The old version is in the Git history
(commit "Browser agent for web-page routers").

### Upgrade the AI
- Use Claude: `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY` in `.env`. No code change.
- Bigger local model: `OLLAMA_MODEL=qwen2.5:14b`. No code change.
- Another provider: a new class with `ask_json()` in `llm.py` + one line in `get_llm()`.
- Smarter answers: more rules/examples in `translator.py`.

### Upgrade the UI
Small changes: edit `index.html`. Big redesign (React, dashboards): build a new front end
that calls the same API URLs (Part 3, Layer 1 table). Python stays the same.

### Add an extra layer (example: "Verification layer" after control)
1. New folder `ibn/verification/` with `verify(plan, kb) → result`
   (e.g. run `show vlan brief` and check VLAN 10 exists).
2. One call in `pipeline.approve()` after `apply_plan`.
3. Show the result in `index.html`.
That's the pattern for any new layer: **new folder + one call in `pipeline.py`**.

### Store more in the knowledge base (VLANs, routes, interfaces as graph nodes)
Add methods to `knowledge/base.py`, implement them in both storages, fill them from
`discovery.py`, and pass them to the AI in `translator.py`.

---

## Part 7: Words you'll see

| Word | Meaning |
|---|---|
| **Python package** | a folder with `__init__.py`, so its files can be imported |
| **import** | using code from another file: `from ibn.intent import translate` |
| **class / method** | a class groups data + functions (methods); e.g. `NetmikoDriver` with `connect()` |
| **contract / interface (ABC)** | a class that only lists the methods others must write (`Driver`, `KnowledgeBase`) |
| **Flask** | a small Python library to build web servers |
| **API** | the list of URLs the page uses to talk to the server |
| **JSON** | text format for data: `{"name": "R1", "ip": "10.0.0.1"}` |
| **schema** | the exact allowed shape of some JSON |
| **LLM / prompt** | the AI model / the instructions + question we send it |
| **Netmiko / Paramiko** | Python libraries for SSH/Telnet to network devices |
| **Neo4j / Cypher** | a graph database / its query language |
| **venv** | a private folder of libraries for this project only |
| **pytest** | the tool that runs the automatic tests |
| **Git / commit / push / pull** | version history / save a checkpoint / upload / download |
