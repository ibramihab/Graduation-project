# Notes for Claude (read automatically in every Claude Code session)

This is a 4-person graduation project: a small, layered **Intent-Based Networking** system
(Python + Flask + one HTML page). Read `README.md` for what it does and
`docs/PROJECT_GUIDE.md` for every file. Team rules are in `docs/TEAM_GUIDE.md`.

## Layer → folder (each teammate usually works in ONE layer)
| Layer | Folder |
|---|---|
| 1 Interface | `ibn/interface/` (web.py, templates/index.html) |
| 2 Intent (AI) | `ibn/intent/` + the `ai_hints` in `ibn/vendors/*.py` |
| 3 Validation | `ibn/validation/` |
| 4 Control | `ibn/control/` |
| 5 Infrastructure | `ibn/infrastructure/` (drivers, discovery) + `ibn/vendors/` |
| Knowledge base | `ibn/knowledge/` |

## Rules
1. **Stay in the layer the user says they work on.** If a change needs another layer's
   files, stop and tell the user first; don't edit them silently.
2. **Never change a contract between layers without telling the user** (other teammates
   depend on it):
   - the plan JSON shape (`PLAN_SCHEMA` in `ibn/intent/translator.py`)
   - `validate()` → `{"ok", "errors", "warnings"}` (`ibn/validation/validator.py`)
   - the `Driver` methods (`ibn/infrastructure/drivers/base.py`)
   - the `KnowledgeBase` methods (`ibn/knowledge/base.py`)
   - the `VendorProfile` fields (`ibn/vendors/base.py`)
   - the `/api/...` URLs (`ibn/interface/web.py`)
3. **Shared files** (`index.html`, `web.py`, `pipeline.py`, `requirements.txt`, `CHANGELOG.md`):
   keep edits small and only where needed.
4. **Run the tests before every commit:** `python -m pytest` (no AI, lab or Neo4j needed).
   Add a test for new behavior in `tests/test_ibn.py`.
5. **Git:** work on the teammate's own branch (`ebraam`, `asmaa`, `menna`, `heba`), never
   commit directly to `main`. Changes reach `main` through a Pull Request.
6. Add one line per change to `CHANGELOG.md` (newest first, 🟢 new / 🟡 changed / 🔴 removed),
   and tell the user which files you changed.
7. Keep it simple: the code is meant to be readable by beginners. Short functions,
   plain names, a comment where something isn't obvious.
8. Never commit `.env` or `data/` (passwords and the user's devices).
