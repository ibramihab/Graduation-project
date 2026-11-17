# Vendors: one folder per vendor

Everything about one kind of device is in its folder, and every layer reads it from there.

```
ibn/vendors/
  base.py                <- what a vendor profile contains (VendorProfile)
  cisco_ios/
    profile.py           <- the rules: login type, show commands, dangerous commands, AI rules
    examples.json        <- the AI's knowledge (RAG): solved requests
    docs/                <- the vendor's documentation as .txt files (RAG; stays on your laptop)
  huawei/
    profile.py           <- examples.json can be added any time, no code change
```

## Adding an example (the best way to make the AI better)
1. Test the commands AND the rollback on the EVE-NG lab first: they must really work.
2. Add it to `examples.json` in the same format as the others:
   `{"intent": "...", "plan": {"summary": "...", "changes": [{"device", "type", "commands", "rollback"}]}}`
   - "config" steps need a rollback that really undoes them; "check" steps have `"rollback": []`.
   - Use different wordings, different names/IPs, and some Arabic requests.
3. Run `python -m pytest`: a test checks that every Cisco example passes the validation layer.

The program notices changed examples by itself (no extra command).

## Adding documentation
Put text files in `<vendor>/docs/` (see the README there). The program cuts them into small pieces and
sends the AI only the closest ones. They are not uploaded to GitHub (copyright and size).

## Adding a vendor
Copy a similar folder, change `profile.py`, add the vendor to the list in `__init__.py`.
`examples.json` is optional: without it the AI just gets the profile's `ai_hints`.
