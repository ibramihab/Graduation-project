# Team Guide

How the four of us (Ebraam, Asmaa, Menna, Heba) work on this project together without
breaking each other's work. No Git experience needed.

> **Our main rule: Claude writes the code, not us.** Each of us asks Claude (Claude Code)
> for changes. Claude edits the files, runs the tests, commits and pushes to **our own
> branch** on GitHub. On our laptops we only **download and run** the project
> (`update.bat` + `start.bat`). We edit by hand in VS Code only in rare cases (section 4C).

---

## 1. Start here (first day)

1. Install:
   - **Python 3.11+** from python.org. ⚠️ In the installer, tick **"Add Python to PATH"**.
   - **Git** from git-scm.com (all default options are fine).
   - **VS Code** from code.visualstudio.com.
2. Accept the **GitHub invitation** (email from GitHub) to `ibramihab/Graduation-project`.
3. Get the project (only once). Open **cmd** in the folder where you want it (e.g. Desktop):
   ```
   git clone https://github.com/ibramihab/Graduation-project
   cd Graduation-project
   git checkout <your-name>
   ```
   (`<your-name>` = `ebraam`, `asmaa`, `menna` or `heba`)
4. Double-click **`start.bat`**. The first time it installs the libraries and opens
   `.env` in Notepad. Fill it in (see section 8 for the AI), save, run `start.bat` again,
   and open http://localhost:5000.
5. *(Optional)* Open the folder in VS Code to **read** the code:
   **File → Open Folder → Graduation-project**.

### No lab? No AI? You can still work
- **No EVE-NG lab:** add devices with vendor **`simulated`** (a fake device in memory),
  and/or set `DRY_RUN=true` in `.env` (shows what would be sent, sends nothing).
- **No AI on your laptop:** see section 8. The tests don't need any AI.
- **Tests:** in the VS Code terminal run `venv\Scripts\python -m pytest`.
  They use a fake AI and fake devices, so they work on every laptop.

---

## 2. Git in 10 words

| Word | Meaning |
|---|---|
| **Repository (repo)** | The project on GitHub |
| **Clone** | Download the repo to your PC once, as a folder connected to GitHub |
| **Commit** | A saved snapshot of your changes, with a short message |
| **Push** | Upload your commits to GitHub |
| **Pull** | Download the newest commits from GitHub |
| **Branch** | A separate line of work. Your branch doesn't affect anyone else's |
| **Pull Request (PR)** | On GitHub: "please merge my branch into `main`". Others can look first |
| **Merge** | Combine one branch's changes into another |
| **Conflict** | Two people changed the **same lines of the same file**: Git asks you to choose |
| **Revert** | A new commit that undoes an old one (history is never deleted) |

---

## 3. Our branches

```
main      ●──────────●──────────────●──────────   always working; only changes through PRs
           \        ↑ PR            ↑ PR
ebraam      ●──●──●─┘               │
asmaa       ●──●──●──●──●───────────┘
menna       ●──●──
heba        ●──●──●──
```

- **`main`** = the official, working version. **Nobody commits to `main` directly.**
- **`ebraam`, `asmaa`, `menna`, `heba`** = one personal branch each. You work only on yours.
- When a piece of your work is finished and tested, you open a **Pull Request** from your
  branch into `main`.

---

## 4. Daily workflow

### 4A. Asking Claude for a change (the normal way)
1. Open a **Claude Code** session on the repo `ibramihab/Graduation-project`, starting from
   **your branch** (e.g. `asmaa`).
2. First message, for example:
   > *"I'm Asmaa. I work on the Intent layer (`ibn/intent/`), on branch `asmaa`.
   > Task: add 5 more examples for ACLs to the Cisco vendor file."*
3. Claude (following `CLAUDE.md`) will:
   - bring the newest `main` into your branch first (and fix conflicts if there are any),
   - make the change **only in your layer**, or ask you first if it needs another layer,
   - run the tests, add a `CHANGELOG.md` line,
   - commit and **push to your branch**, and tell you which files it changed.
   (If Claude says it can only push to a `claude/...` branch, ask it to open a Pull Request
   from that branch **into your branch**, then merge it on GitHub.)
4. **Only one Claude session per branch at a time.** Two sessions changing the same branch at
   once can overwrite each other.

### 4B. Trying the change on your laptop
1. Double-click **`update.bat`** (downloads the newest version of **your** branch).
2. Double-click **`start.bat`** and test it in the browser.
3. Something wrong? Tell Claude what you saw (a screenshot helps) and it fixes it.

### 4C. Editing by hand in VS Code (rare cases only)
1. **First** run `update.bat` (start from the newest version).
2. Edit, then Source Control tab → message → **Commit** → **Sync Changes** (push).
3. Tell Claude in your next session: *"I changed X by hand"*.
- ⚠️ Never leave hand edits uncommitted: `update.bat` can't download while your files have
  unsaved Git changes, and it will show an error.

### 4D. When a feature is finished: into `main`
1. Ask Claude: *"Open a Pull Request from `asmaa` into `main`, describing what changed."*
2. GitHub runs the tests automatically on the PR (✅ or ❌, section 9).
3. A teammate opens the PR on GitHub → **Files changed** → looks → **Approve**.
4. Someone clicks **Merge pull request**. (A person always does the merge, not Claude.)
5. Write in the group chat: *"merged X into main"*. Everyone's next Claude session will
   bring it into their branch automatically (step 4A.3).

---

## 5. Who owns what

Each person mainly works in **one layer = one folder**. Fill in the names:

| Layer | Folder(s) | Owner |
|---|---|---|
| 1 Interface + Knowledge base | `ibn/interface/`, `ibn/knowledge/` | |
| 2 Intent (AI) | `ibn/intent/`, the `ai_hints` in `ibn/vendors/*.py` | |
| 3 Validation + 4 Control | `ibn/validation/`, `ibn/control/` | |
| 5 Infrastructure + discovery | `ibn/infrastructure/`, `ibn/vendors/` | |

**Shared files** (everyone may need them): `ibn/interface/templates/index.html`,
`ibn/interface/web.py`, `ibn/pipeline.py`, `requirements.txt`, `CHANGELOG.md`,
`tests/test_ibn.py`.
→ Keep your edits there small, pull `main` often, and say in the group chat when you
change them.

---

## 6. The contracts between layers (don't change them alone)

The layers talk to each other through a few fixed "shapes". As long as these stay the
same, you can rewrite everything **inside** your layer and nobody else is affected.

| Contract | Used by | File |
|---|---|---|
| **Plan JSON**: `{summary, changes: [{device, type, commands, rollback}]}` | Intent → Validation → Control | `ibn/intent/translator.py` (`PLAN_SCHEMA`) |
| **Validation result**: `{ok, errors, warnings}` | Validation → pipeline, web page | `ibn/validation/validator.py` |
| **Driver methods**: `connect`, `disconnect`, `get_config`, `send_config`, `run_commands`, `get_interfaces`, `get_neighbors` | Control, discovery → drivers | `ibn/infrastructure/drivers/base.py` |
| **Knowledge base methods**: `add_device`, `get_device`, `list_links`, `record_change`, ... | everyone | `ibn/knowledge/base.py` |
| **Vendor profile fields** | intent, validation, drivers | `ibn/vendors/base.py` |
| **API URLs**: `/api/intent`, `/api/approve/<id>`, `/api/devices`, ... | web page ↔ server | `ibn/interface/web.py` |

Need to change one? **Agree with the team first**, then change it **and** every place that
uses it in the same PR.

---

## 7. Merging and conflicts

- Git merges **automatically** when people changed **different files**, or different parts
  of the same file. Because each of us works in a different folder, most merges are
  automatic.
- A **conflict** happens only when two people changed **the same lines**. Git marks them:
  ```
  <<<<<<< HEAD
  your version
  =======
  their version
  >>>>>>> origin/main
  ```
- **Who fixes it:** Claude, when it brings `main` into your branch at the start of a
  session. It keeps both changes when possible and asks you if they really contradict.
  (By hand in VS Code: open the file → **Resolve in Merge Editor** → choose → **Complete
  Merge** → commit → push.)
- **No conflict ≠ no bug.** After every merge, run the tests. They check that the layers
  still work together.

---

## 8. AI options for every laptop

| Option | How | Cost | Quality |
|---|---|---|---|
| **A. Share one Ollama over Wi-Fi/LAN** | On the laptop that runs Ollama: Windows search → "environment variables" → add **`OLLAMA_HOST`** = `0.0.0.0` → restart Ollama → allow it in Windows Firewall when asked. On the other laptops, in `.env`: `LLM_PROVIDER=ollama`, `OLLAMA_URL=http://<that-laptop's-IP>:11434`, `OLLAMA_MODEL=qwen2.5:7b` | free | same model for all |
| **B. Claude API** | `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY=...`. In the Anthropic console, set a **monthly spending limit** | small per request | best |
| **C. Smaller local model** | `ollama pull qwen2.5:3b`, then `OLLAMA_MODEL=qwen2.5:3b` | free | weaker |
| **D. No AI** | Work with `pytest` + `simulated` devices. Enough for validation, control, discovery and UI work | free | — |

**Database:** keep `KB_BACKEND=file` (a JSON file, nothing to install). Neo4j is optional.

---

## 9. Automatic tests on GitHub

`.github/workflows/tests.yml` makes GitHub run `pytest` on its own servers for every push
and every Pull Request. You see a ✅ or ❌ next to the commit and on the PR page.
**Don't merge a PR with a ❌.** Click the ❌ → *Details* to see which test failed.

---

## 10. Working with Claude in a team

- **`CLAUDE.md`** (in the main folder) is read automatically by Claude Code in every
  session. It tells Claude our rules: stay in your layer, don't change contracts silently,
  run the tests, work on your branch.
- Start each session with one sentence, for example:
  > *"I'm Menna. I work on the Validation and Control layers only (`ibn/validation/`,
  > `ibn/control/`), on branch `menna`. Don't edit other layers without asking me."*
- Claude tells you **which files it changed**. Read its summary, and if a change touches
  a shared file or a contract, tell the group.
- You can see exactly what changed on GitHub: your branch → **Commits** → click a commit.

---

## 11. Ideas for each layer

**Interface + Knowledge base**
- Nicer page: separate tabs (Devices, Topology, History), progress messages.
- User login (there is none yet).
- Topology: colors for up/down, link labels with interface names.
- Neo4j for the demo (the storage contract already supports it).

**Intent (AI)**
- **An evaluation set first:** `tests/intents.json` with ~50 requests + the expected
  commands, and a small script that scores any AI model. Then every improvement is a number.
- More and better examples in the vendor files (cheapest, strongest improvement).
- **RAG:** a new `ibn/intent/retriever.py` that searches command documentation / notes and
  adds only the relevant parts to the prompt. Stays inside `ibn/intent/`.
- More AI providers (OpenAI-compatible APIs, Gemini...) as new classes in `llm.py`.

**Validation + Control**
- **Verify after applying:** run `show` commands and check the intent really happened.
- Check for IP-address conflicts using the knowledge base.
- `write memory` after a successful change (optional setting).
- Show a before/after config difference.

**Infrastructure + discovery**
- LLDP and same-subnet link discovery (works for non-Cisco devices).
- Read the hostname automatically, so the user only types the IP.
- Detect the vendor automatically (SSH banner, SNMP).
- Log in to many devices in parallel.

---

## 12. Checklist before asking for a PR into `main`

- [ ] My branch has the newest `main` in it (Claude does this at the start of each session).
- [ ] The tests pass (✅ on my branch on GitHub), and there's a test for the new feature.
- [ ] I tried it on my laptop with `update.bat` + `start.bat`.
- [ ] I only changed files in **my layer** (or told the team about shared files).
- [ ] I didn't change a **contract** (section 6) without agreeing with the team.
- [ ] I added a line to `CHANGELOG.md`.
- [ ] I didn't upload `.env` or `data/` (Git ignores them automatically; don't force it).
