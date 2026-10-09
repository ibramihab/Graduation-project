# Simple IBN (Intent-Based Networking)

You type what you want in plain English, for example:

> Create VLAN 10 named Sales on SW1

The system turns it into device commands, checks they are safe, shows them to
you, and when you click **Approve** it logs in to the device and applies them.
If something fails, it undoes the change automatically.

The project is deliberately small (about 1000 lines of Python) so you can read
all of it. Every layer is one folder, and every "kind of thing" (LLM, vendor,
database) can be swapped or extended without touching the other layers.

---

## 1. The layers

```
  1. Interface       ibn/interface/        web page: type + approve          ─┐
          │                                                                  │
  2. Intent          ibn/intent/           LLM turns English into a plan     ─┤
          │                                                                  │   Knowledge base
  3. Validation      ibn/validation/       checks the plan is safe           ─┤   ibn/knowledge/
          │                                                                  │   (graph: devices, links,
  4. Control         ibn/control/          applies it, rolls back on error   ─┤    state, backups, history)
          │                                                                  │
  5. Infrastructure  ibn/infrastructure/   drivers + discovery               ─┘
```

`ibn/pipeline.py` is the glue (about 40 lines). It calls the layers in order:

```
text ─► intent.translate() ─► validation.validate() ─► [you click Approve] ─► control.apply_plan() ─► drivers
```

### What happens step by step

| Step | File | What it does |
|---|---|---|
| You type a request | `interface/templates/index.html` | The page sends it to `POST /api/intent` |
| **Intent** | `intent/translator.py` | Sends the request + the device list with their interface IPs (no passwords) to the LLM. The LLM must answer in a fixed JSON shape: a list of steps, each with a device, a `type`, `commands` and `rollback` (undo) commands. Type `config` changes the device (configuration mode); type `check` runs read-only commands like `ping` / `show` (normal mode, no rollback). |
| **Validation** | `validation/validator.py` + `rules.py` | Device exists? Vendor supported? Device up? Commands present? Any dangerous command (`reload`, `erase`, `no username`, ...)? Errors **block** the plan; warnings are shown to you. |
| You click Approve | `pipeline.py` | The plan is validated **again** (the network could have changed). |
| **Control** | `control/controller.py` | For each `config` step: connect, save a config backup to the knowledge base, send commands. If any device fails, the rollback runs on every device already changed. `check` steps just run and show their output. Everything goes into the device's history. |
| **Infrastructure** | `infrastructure/drivers/` | The code that actually talks to devices (see below). |

---

## 2. Run it (first time)

You need **Python 3.10+**.

```bash
# 1. get the code and install the libraries
git clone <this repo>
cd Graduation-project
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. settings
cp .env.example .env                # Windows: copy .env.example .env
#    open .env and paste your ANTHROPIC_API_KEY

# 3. start
python run.py
#    open http://localhost:5000
```

### Try it without any real device

1. In **Add / edit a device**: name `SW1`, IP `10.0.0.2`, vendor `simulated`, Save.
2. Add `R1` the same way, then link `R1` and `SW1`.
3. Type `Create VLAN 10 named Sales on SW1` → **Make a plan** → **Approve & apply**.
4. Click **History** on SW1 to see what was recorded.
5. To see a rollback: ask for something on two devices, and include a command
   containing the word `invalid`. The simulated device rejects it and the
   system undoes everything.

### Try it with real / emulated devices

Use GNS3, EVE-NG or real lab gear. (Cisco Packet Tracer will **not** work:
its devices can't be reached by SSH from your PC.) On a Cisco router enable SSH, then add the device
with vendor `cisco_ios`, its management IP, and protocol `ssh` or `telnet`.
The login comes from `DEVICE_USERNAME` / `DEVICE_PASSWORD` in `.env`.

Set `DRY_RUN=true` in `.env` if you want to see everything work without
sending anything to the devices.

### Run the tests

```bash
pytest
```

Tests use a fake LLM and simulated devices, so they need no API key and no network.

---

## 3. The knowledge base (graph database)

The network is naturally a graph, so we store it as one:

```
(R1:Device)-[:CONNECTED_TO]-(SW1:Device)
(SW1:Device)-[:HAS_CHANGE]->(:Change {time, intent, commands, success})
Device properties: name, ip, vendor, protocol, state (up/down), last_config (backup)
```

There are two storage options with the **same** methods (`knowledge/base.py`):

| `KB_BACKEND` | File | When to use |
|---|---|---|
| `file` (default) | `knowledge/file_graph.py` | Learning. Nothing to install. Saves to `data/knowledge.json`. |
| `neo4j` | `knowledge/neo4j_graph.py` | The real graph database. |

To use Neo4j (needs [Docker](https://docs.docker.com/get-docker/)):

```bash
docker compose up -d                # starts Neo4j
# in .env:  KB_BACKEND=neo4j
python run.py
```

Open http://localhost:7474 (user `neo4j`, password `password123`) and run
`MATCH (n) RETURN n` to **see** your network as a graph.

`TEST_NEO4J=1 pytest` also runs all the tests against Neo4j. **Warning:** it
deletes all devices in that Neo4j, so only use it on an empty test database.

---

## 4. Topology discovery

Kept as simple as possible (`infrastructure/discovery.py`):

| Button | How it works |
|---|---|
| **Scan (ping)** | Pings every address in a subnet (64 at a time). Each answer becomes a device called `host-<ip>`, and we check if ports 22/23/80 are open (SSH/Telnet/Web). The vendor is `unknown`: click **Edit** to set it and rename it. |
| **Find links & IPs (CDP)** | Logs in to each device, saves its interface IPs (`show ip interface brief`, so the AI knows them) and runs `show cdp neighbors detail` (Cisco). Neighbors we know become links in the graph. |
| **Refresh up/down** | Pings every known device and saves `up` / `down`. Validation refuses to change a device that is down. |

On Linux, `ping` must be installed (`sudo apt install iputils-ping`).

---

## 5. How devices are reached (no SDN, traditional methods)

Each way of talking to a device is a **driver** class with the same 4 methods
(`infrastructure/drivers/base.py`): `connect`, `disconnect`, `get_config`,
`send_config`. The control layer never knows which driver it is using.

| vendor value | Driver | How |
|---|---|---|
| `cisco_ios`, `cisco_nxos`, `arista_eos`, `huawei`, `mikrotik_routeros` | `netmiko_cli.py` | SSH or Telnet with the [Netmiko](https://github.com/ktbyers/netmiko) library |
| `web_gui` | `web_gui.py` | For home routers with only a web page: downloads the page, finds the HTML forms, asks the LLM which fields to fill, submits the form. Its "commands" are English, e.g. `set wifi name to Home5G`. Give the device a `url` like `http://192.168.1.1/wireless.html`. |
| `simulated` | `simulated.py` | A fake device in memory, for learning and tests |

The web GUI driver is the simplest version that works for plain HTML forms with
basic login. Routers that build the page with JavaScript need a real browser
(see "Ideas" below).

---

## 6. How to grow it (where each upgrade goes)

### Add a new CLI vendor (e.g. Juniper, Fortinet, HP)
1. If Netmiko supports it ([list](https://github.com/ktbyers/netmiko/blob/develop/PLATFORMS.md)),
   add one line to `NETMIKO_TYPES` in `infrastructure/drivers/netmiko_cli.py`:
   `"fortinet": ("fortinet", "show full-configuration"),`
2. Add it to the vendor drop-down in `interface/templates/index.html`.
3. Optional: add its dangerous commands in `validation/rules.py`.

Juniper needs a `commit` after the commands: make a small `JunosDriver(NetmikoDriver)`
that overrides `send_config` to call `self.conn.commit()`, and register it in
`drivers/__init__.py`.

### Add a new access method (REST API, NETCONF, SNMP)
Write a class like `class RestApiDriver(Driver)` with the 4 methods, then add
one line to `DRIVERS` in `infrastructure/drivers/__init__.py`.

### Add SDN later
SDN fits the same idea: write `OnosDriver` / `OpenDaylightDriver` whose
`send_config` calls the controller's REST API instead of a device. Register it
as a new vendor (e.g. `sdn_onos`). The intent, validation and control layers
stay the same.

### Use a local LLM instead of the API key
1. Install [Ollama](https://ollama.com) and run `ollama run llama3.1`.
2. In `.env`: `LLM_PROVIDER=ollama`.
That's it. Any other LLM = a new class with an `ask_json()` method in `intent/llm.py`.

### Better validation
- Check for IP address conflicts using the knowledge base.
- Test the config first in a lab copy of the network ([Batfish](https://www.batfish.org/), GNS3).
- After applying, run `show` commands to verify the intent really happened.

### Better discovery
- LLDP (works for non-Cisco devices), SNMP, ARP/MAC tables.
- Detect the vendor automatically (SSH banner, SNMP sysDescr).

### Other ideas
- Users and login on the web page (there is none yet, so run it only on a lab network).
- Store device passwords encrypted per device (now there is one shared login in `.env`).
- A JavaScript-capable browser (Playwright) for web-GUI routers.
- Monitoring loop: re-check the intent every few minutes and fix drift ("closed loop" IBN).

---

## 7. File map

```
run.py                         start the web server
ibn/
  settings.py                  reads .env
  pipeline.py                  connects the layers in order
  interface/web.py             URLs the page calls (Flask)
  interface/templates/index.html   the web page
  intent/llm.py                Claude (cloud) and Ollama (local) LLMs
  intent/translator.py         prompt + JSON shape of a plan
  validation/validator.py      the checks
  validation/rules.py          dangerous commands per vendor
  control/controller.py        apply + rollback + history
  infrastructure/discovery.py  ping scan, port check, CDP links
  infrastructure/drivers/      one file per way of talking to devices
  knowledge/base.py            the knowledge base methods
  knowledge/file_graph.py      graph in a JSON file
  knowledge/neo4j_graph.py     graph in Neo4j
tests/test_ibn.py              tests for the whole flow
docker-compose.yml             starts Neo4j
```
