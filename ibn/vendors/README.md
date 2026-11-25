# Vendors: one folder per vendor

Everything about one kind of device is in its folder, and every layer reads it from there.

```
ibn/vendors/
  base.py                <- what a vendor profile contains (VendorProfile)
  cisco_ios/
    profile.py           <- the rules: login type, show commands, dangerous commands, AI rules
    docs/                <- the AI's knowledge (RAG): one .md file per topic, notes + solved examples
  huawei/
    profile.py           <- a docs/ folder can be added any time, no code change
```

## Adding knowledge (the best way to make the AI better)
Open the topic's file in `<vendor>/docs/` (e.g. `static_routes.md`) and add a note or an example under
the right `## ` heading. The format is explained in `cisco_ios/docs/README.md`.
1. Test the commands AND the undo commands first: they must really work.
2. At most 3 examples per heading: for a new case, add a new heading.
3. Run `python -m pytest`: a test checks the format and that every example passes the validation layer.

The program notices changed files by itself (no extra command).

## Adding a vendor
Copy a similar folder, change `profile.py`, add the vendor to the list in `__init__.py`.
`docs/` is optional: without it the AI just gets the profile's `ai_hints`.
