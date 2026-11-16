# Knowledge for the AI (RAG)

Before the AI makes a plan, the program finds the solved examples here that look most like the
request and puts them in the prompt. More good examples = better plans.

```
knowledge/
  cisco_ios/            <- one folder per vendor (same name as in the vendor list)
    examples.json       <- solved requests: {"intent": ..., "plan": {...}}
  huawei/ ...           <- another vendor later: same layout, no code change
```

## Adding an example
1. Test the commands AND the rollback on the EVE-NG lab first: they must really work.
2. Add it to `examples.json` in the same format as the others:
   - "config" steps need a rollback that really undoes them; "check" steps have `"rollback": []`.
   - Use different wordings, different names/IPs, and some Arabic requests.
3. Run `python -m pytest`: a test checks that every example passes the validation layer.

The program notices changed examples by itself (no extra command).
