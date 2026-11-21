"""Pre-deployment analysis with Batfish (https://www.batfish.org) - Cisco IOS / IOS-XE for now.

Batfish reads device configs and builds a model of the whole network (routing tables,
ACLs, how a packet would travel) WITHOUT touching any device. We give it two snapshots:

    baseline  = the configs of the network today
    proposed  = the same configs with the plan's commands applied to them

and compare them:
    validity      - can Batfish read the new config? lines it doesn't understand?
    references    - something used but never defined (e.g. an ACL applied but missing)
    routing       - routes the network would lose, forwarding loops
    reachability  - traffic that worked before and would be dropped after the change
    ACLs          - ACL lines that can never match (hidden by an earlier line)
Each check gives PASS, WARNING or FAIL. A FAIL becomes a validation error (it blocks the
plan), a WARNING is shown to the user. Devices Batfish can't analyze are listed as SKIPPED
(not a problem with the plan, so not a warning).

Where the baseline configs come from (we never invent them):
    1. a device's "last_config" in the knowledge base (the backup taken before a change)
    2. otherwise a file <device name>.cfg in the folder BATFISH_CONFIG_DIR (from .env)
A device with neither is not analyzed (SKIPPED, with the reason).

Batfish runs as a separate server (Docker):  docker run -d -p 9996:9996 batfish/batfish
and is OFF until BATFISH_HOST is set in .env. Without it the result is just "SKIPPED".
"""
import hashlib
import logging
import os
import re
import tempfile

from .. import settings
from .config_model import EXITS, ON_OFF, TOP_LEVEL, section_keys, setting_key

SUPPORTED = {"cisco_ios"}       # vendors Batfish checks for now (IOS / IOS-XE syntax)
MAX_LISTED = 5                  # longest list shown in one message
_CACHE: dict[str, dict] = {}    # same configs + same plan -> same answer (approve re-validates)


def analyze(plan: dict, kb) -> dict:
    """Returns {"status": "PASS" | "WARNING" | "FAIL" | "SKIPPED",
                "results": [{"check": "...", "status": "PASS" | "WARNING" | "FAIL", "message": "..."}]}"""
    changes = [c for c in plan.get("changes", []) if c.get("type") != "check"]
    if not settings.BATFISH_HOST:
        return _skipped("Batfish is off (set BATFISH_HOST in .env to turn it on)")
    if not changes:
        return _skipped("no configuration changes to analyze")

    baseline = baseline_configs(kb)
    proposed, results = dict(baseline), []
    for change in changes:
        name = change.get("device", "?")
        device = kb.get_device(name) or {}
        if device.get("vendor") not in SUPPORTED:
            results.append(_result("coverage", "SKIPPED", f"{name}: not analyzed, the Batfish check "
                                   f"supports Cisco IOS only (this device is '{device.get('vendor')}')"))
        elif name not in baseline:
            results.append(_result("coverage", "SKIPPED", f"{name}: not analyzed, there is no config for "
                                   "it (no backup yet, and no file in BATFISH_CONFIG_DIR)"))
        else:
            proposed[name] = apply_commands(proposed[name], change.get("commands", []))
    if proposed == baseline:  # nothing Batfish can analyze
        return {"status": "SKIPPED", "results": results, "reason": "no Cisco IOS device with a config to analyze"}

    key = hashlib.sha256(repr((sorted(baseline.items()), sorted(proposed.items()))).encode()).hexdigest()
    if key not in _CACHE:
        try:
            _CACHE[key] = _run_batfish(baseline, proposed, key[:12])
        except Exception as error:  # server down, wrong address...: report it, don't crash
            return {"status": "WARNING", "results": results + [_result(
                "batfish", "WARNING", f"the Batfish analysis could not run ({type(error).__name__}: {error})")]}
    results = results + _CACHE[key]
    return {"status": _overall(results), "results": results}


def baseline_configs(kb) -> dict[str, str]:
    """{device name: config text} for every Cisco IOS device we have a REAL config for."""
    configs = {}
    folder = settings.BATFISH_CONFIG_DIR
    if folder and os.path.isdir(folder):
        for file in sorted(os.listdir(folder)):
            if file.lower().endswith((".cfg", ".txt", ".conf")):
                with open(os.path.join(folder, file), encoding="utf-8", errors="replace") as f:
                    configs[os.path.splitext(file)[0]] = f.read()
    names = {d["name"].lower(): d for d in kb.list_devices()}
    for stem in list(configs):  # use the knowledge base's spelling of the name ("r1.cfg" -> "R1")
        device = names.get(stem.lower())
        if device and device["name"] != stem:
            configs[device["name"]] = configs.pop(stem)
    for device in kb.list_devices():
        backup = device.get("last_config") or ""
        if device.get("vendor") in SUPPORTED and re.search(r"^(hostname|interface) ", backup, re.M):
            configs[device["name"]] = backup  # a real backup is newer than a file
    return configs


# ---------------- applying the plan to a config text ----------------
def apply_commands(config: str, commands: list[str]) -> str:
    """The config text after the commands, like the device would save it.
    'interface X' + settings go into the existing interface block (replacing old values),
    'no ...' removes lines or whole blocks, top-level lines are added at the end."""
    blocks = _read_blocks(config)
    current = []  # the block(s) the next lines go into (an interface, a vlan...)
    for raw in commands:
        line = " ".join(raw.split())
        low = line.lower()
        if not line or low in EXITS:
            current = []
            continue
        negated = low.startswith("no ")
        body = line[3:] if negated else line
        keys = section_keys(body.lower(), "ios")
        if keys:
            if negated:
                blocks = [b for b in blocks if b["key"] not in keys]
                current = []
            else:
                current = [_find_or_add(blocks, key, body if len(keys) == 1 else f"vlan {key[5:]}")
                           for key in keys]
        elif current and not TOP_LEVEL.match(body.lower()):
            for block in current:
                _set_child(block, body, negated)
        else:
            current = []
            _set_top(blocks, body, negated)
    return _write_blocks(blocks)


def _read_blocks(config: str) -> list[dict]:
    """Config text -> [{"header": "interface Ethernet0/0", "key": ..., "children": [" ip address ..."]}]"""
    blocks = []
    for raw in config.splitlines():
        text = raw.rstrip()
        if not text.strip() or text.strip() in ("!", "end"):
            continue
        if text[0].isspace() and blocks and blocks[-1]["key"]:
            blocks[-1]["children"].append(text)
        else:
            keys = section_keys(text.strip().lower(), "ios")
            blocks.append({"header": text.strip(), "key": keys[0] if keys else None, "children": []})
    return blocks


def _write_blocks(blocks: list[dict]) -> str:
    lines = []
    for block in blocks:
        lines.append(block["header"])
        lines += block["children"]
        if block["key"]:
            lines.append("!")
    return "\n".join(lines + ["end", ""])


def _find_or_add(blocks, key, header):
    for block in blocks:
        if block["key"] == key:
            return block
    block = {"header": header, "key": key, "children": []}
    blocks.append(block)
    return block


def _set_child(block, body, negated):
    key = setting_key(body.lower(), block["key"])
    block["children"] = [c for c in block["children"]
                         if not _same_setting(setting_key(c.strip().lower(), block["key"]), key)
                         and c.strip().lower() not in (body.lower(), f"no {body.lower()}")]
    if not negated:
        block["children"].append(" " + body)
    elif key in ON_OFF and key != "shutdown":
        block["children"].append(" no " + body)   # e.g. "no switchport" is a real setting
    # "no shutdown" = just remove "shutdown" (up is the default)


def _set_top(blocks, body, negated):
    key = setting_key(body.lower(), None)
    blocks[:] = [b for b in blocks if b["key"] or not _same_setting(setting_key(b["header"].lower(), None), key)]
    if not negated:
        blocks.append({"header": body, "key": None, "children": []})


def _same_setting(existing: str, key: str) -> bool:
    return existing == key or existing.startswith(key + " ")


# ---------------- running Batfish ----------------
def _run_batfish(baseline: dict, proposed: dict, tag: str) -> list[dict]:
    from pybatfish.client.session import Session  # imported here: pybatfish is only needed when Batfish is on
    logging.getLogger("pybatfish").setLevel(logging.ERROR)
    bf = Session(host=settings.BATFISH_HOST)
    bf.set_network(settings.BATFISH_NETWORK)
    base_name, new_name = f"base-{tag}", f"plan-{tag}"
    with tempfile.TemporaryDirectory() as folder:
        for name, configs in ((base_name, baseline), (new_name, proposed)):
            os.makedirs(os.path.join(folder, name, "configs"))
            for device, text in configs.items():
                with open(os.path.join(folder, name, "configs", f"{device}.cfg"), "w") as f:
                    f.write(text)
            bf.init_snapshot(os.path.join(folder, name), name=name, overwrite=True)
    try:
        names = {d.lower(): d for d in proposed}  # Batfish writes host names in lowercase
        return (_validity(bf, base_name, new_name, names)
                + _references(bf, base_name, new_name)
                + _routing(bf, base_name, new_name, names)
                + _loops(bf, base_name, new_name)
                + _reachability(bf, base_name, new_name, names)
                + _acls(bf, base_name, new_name, names))
    finally:
        for name in (base_name, new_name):
            try:
                bf.delete_snapshot(name)
            except Exception:
                pass


def _rows(bf, question, snapshot, **parameters) -> list[dict]:
    return getattr(bf.q, question)(**parameters).answer(snapshot=snapshot).frame().to_dict("records")


def _new_rows(bf, question, base, new, fields, **parameters) -> list[dict]:
    """Rows of a question that appear in the proposed snapshot but not in the baseline."""
    def key(row):
        return tuple(str(row.get(f)) for f in fields)
    old = {key(r) for r in _rows(bf, question, base, **parameters)}
    return [r for r in _rows(bf, question, new, **parameters) if key(r) not in old]


def _validity(bf, base, new, names):
    results = []
    for row in _rows(bf, "fileParseStatus", new):
        if row["Status"] == "FAILED":
            results.append(_result("validity", "FAIL", f"Batfish could not read the new config "
                                   f"{row['File_Name']} at all"))
    for row in _new_rows(bf, "parseWarning", base, new, ("Filename", "Text")):
        results.append(_result("validity", "WARNING", f"{_device_of(row['Filename'], names)}: Batfish does "
                               f"not understand '{row['Text']}' ({row.get('Comment') or 'line ignored'}); "
                               "check the command"))
    for row in _new_rows(bf, "initIssues", base, new, ("Nodes", "Type", "Details", "Line_Text")):
        if row["Type"] == "Parse warning":
            continue  # already reported above by parseWarning
        results.append(_result("validity", "WARNING", f"{_nodes(row['Nodes'], names)}: {row['Details']}"))
    return results or [_result("validity", "PASS", "the new configs are valid (every line understood)")]


def _references(bf, base, new):
    results = []
    for row in _new_rows(bf, "undefinedReferences", base, new, ("File_Name", "Struct_Type", "Ref_Name")):
        results.append(_result("references", "FAIL", f"{_device_of(row['File_Name'])}: "
                               f"{row['Struct_Type']} '{row['Ref_Name']}' is used ({row['Context']}) but "
                               "never defined"))
    return results or [_result("references", "PASS", "everything that is used is defined")]


def _routing(bf, base, new, names):
    def routes(snapshot):
        return {(r["Node"], r["VRF"], r["Network"]): r for r in _rows(bf, "routes", snapshot)}
    before, after = routes(base), routes(new)
    lost = [before[k] for k in sorted(set(before) - set(after))]
    gained = len(set(after) - set(before))
    if not lost:
        return [_result("routing", "PASS", f"no route is lost ({gained} new route(s))")]
    listed = [f"{names.get(r['Node'], r['Node'])} loses {r['Network']} ({r['Protocol']})" for r in lost]
    return [_result("routing", "WARNING", _join(listed) + f" - {len(lost)} route(s) lost in total")]


def _loops(bf, base, new):
    def count(snapshot):
        return len(_rows(bf, "detectLoops", snapshot))
    added = count(new) - count(base)
    if added > 0:
        return [_result("routing", "FAIL", f"the change creates {added} forwarding loop(s): packets "
                        "would circle between routers")]
    return [_result("routing", "PASS", "no forwarding loops")]


def _reachability(bf, base, new, names):
    answer = bf.q.differentialReachability().answer(snapshot=new, reference_snapshot=base)
    lost, gained = [], 0
    for row in answer.frame().to_dict("records"):
        now = _disposition(row["Snapshot_Traces"])
        before = _disposition(row["Reference_Traces"])
        if _success(before) and not _success(now):
            flow = row["Flow"]
            lost.append(f"{flow.srcIp} -> {flow.dstIp} (from {names.get(flow.ingressNode, flow.ingressNode)})"
                        f" worked before, now {now.replace('_', ' ').lower()}")
        elif _success(now) and not _success(before):
            gained += 1
    if lost:
        return [_result("reachability", "WARNING", "traffic would be cut: " + _join(lost)
                        + ". If this is what you want (e.g. a block rule), ignore this warning")]
    extra = f" ({gained} new path(s) open)" if gained else ""
    return [_result("reachability", "PASS", "no traffic that works today would be dropped" + extra)]


def _acls(bf, base, new, names):
    results = []
    for row in _new_rows(bf, "filterLineReachability", base, new, ("Sources", "Unreachable_Line")):
        results.append(_result("acl", "WARNING", f"{_nodes(row['Sources'], names)}: the ACL line "
                               f"'{row['Unreachable_Line']}' can never match (hidden by "
                               f"'{', '.join(map(str, row['Blocking_Lines'] or []))}')"))
    return results or [_result("acl", "PASS", "every ACL line can match (no hidden lines)")]


# ---------------- small helpers ----------------
def _disposition(traces) -> str:
    return str(traces[0].disposition) if traces else "NO_TRACE"


def _success(disposition: str) -> bool:
    return disposition in ("ACCEPTED", "DELIVERED_TO_SUBNET", "EXITS_NETWORK")


def _device_of(file_name: str, names: dict | None = None) -> str:
    stem = os.path.splitext(os.path.basename(str(file_name)))[0]
    return (names or {}).get(stem.lower(), stem)


def _nodes(nodes, names=None) -> str:
    """['r3: BLOCK-LAN1'] -> 'R3: BLOCK-LAN1' (Batfish writes device names in lowercase)."""
    items = list(nodes) if isinstance(nodes, (list, tuple)) or hasattr(nodes, "__iter__") \
        and not isinstance(nodes, str) else [nodes]
    shown = []
    for item in map(str, items):
        node, _, rest = item.partition(":")
        shown.append((names or {}).get(node, node) + (":" + rest if rest else ""))
    return ", ".join(shown)


def _join(items: list[str]) -> str:
    more = f" (and {len(items) - MAX_LISTED} more)" if len(items) > MAX_LISTED else ""
    return "; ".join(items[:MAX_LISTED]) + more


def _result(check: str, status: str, message: str) -> dict:
    return {"check": check, "status": status, "message": message}


def _overall(results: list[dict]) -> str:
    """FAIL if any check failed, else WARNING if any warned, else PASS (SKIPPED items don't count)."""
    statuses = {r["status"] for r in results}
    return "FAIL" if "FAIL" in statuses else "WARNING" if "WARNING" in statuses else "PASS"


def _skipped(reason: str) -> dict:
    return {"status": "SKIPPED", "results": [], "reason": reason}
