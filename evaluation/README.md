# Testing the AI automatically

```
python evaluation\run_tests.py                  every test, RAG off then on
python evaluation\run_tests.py --rag on         only with RAG
python evaluation\run_tests.py --only dhcp trunk
```

- Uses your AI settings from `.env` (`LLM_PROVIDER`, `OLLAMA_MODEL`...). Ollama must be running.
- Uses the fixed test network in `lab.json`, NOT your devices, and sends nothing to any device.
- Each plan gets a mark:
  - **PASS**: every required command is there, nothing forbidden, validation OK, rollback present
  - **HALF**: right commands, smaller problem (validation errors, no rollback...)
  - **FAIL**: required commands missing, forbidden command, no plan, or an error
- Results: printed, and saved in `data\evaluation\<date>_<model>.csv` (opens in Excel).

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
(`ibn/vendors/<vendor>/examples.json`), or the AI just copies an example and the score lies.

Also: every plan made on the web page is saved in `data\plans.csv` (setting `PLAN_LOG`).
