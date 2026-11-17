"""Risk scoring: how dangerous is this plan? A score from 0 to 100 + a level.

The score is the sum of six parts (the maximum of each part in brackets):
  command severity       (30)  what the commands do: add < change/remove < routing <
                               "look twice" commands (shutdown, ACLs...) < blocked commands
  device criticality     (20)  single point of failure > hub (3+ links) > normal > edge device
  topology impact        (15)  a risky command on a single point of failure splits the network
  affected devices       (15)  the share of the network that the change can reach or cut off
  rollback               (10)  missing or incomplete rollback = a failure can't be fully undone
  conflicts/prerequisites(10)  conflicts with the current network, missing prerequisites,
                               or problems found by Batfish

Levels:  0-24 LOW   25-49 MEDIUM   50-74 HIGH   75-100 CRITICAL
Every part gives a reason, so the user sees WHY the plan got its score.
A CRITICAL score does not block the plan: the user decides when approving.
"""
import re

from ..knowledge.graph_analysis import build_graph, critical_devices, impact
from ..vendors import get_vendor

LEVELS = [(75, "CRITICAL"), (50, "HIGH"), (25, "MEDIUM"), (0, "LOW")]
ROUTING = re.compile(r"^(no |undo )?(router |ip route|ipv6 route|ip route-static|ospf|bgp|"
                     r"/ip route|/routing|config router)")
REMOVAL = re.compile(r"^(no|undo|delete|unset|purge)\b|\bremove\b|disabled=yes")


def assess(plan: dict, kb, findings: dict) -> dict:
    """findings: counts from the checks, e.g. {"rollback_errors": 0, "conflict_warnings": 2, ...}"""
    config = [c for c in plan.get("changes", []) if c.get("type") != "check" and kb.get_device(c.get("device"))]
    if not config:
        return {"score": 0, "level": "LOW",
                "reasons": ["Read-only plan (or nothing to apply): nothing on the network changes."]}
    graph = build_graph(kb)
    spof = set(critical_devices(kb))
    risky = _risky_devices(config, kb)
    severity = _severity(config, kb)
    parts = [
        severity,
        _criticality(config, graph, spof, harmless=severity[0] < 15),
        _topology(config, graph, spof, risky, findings.get("cut_access", [])),
        _affected(config, kb, spof, risky),
        _rollback(findings),
        _conflicts(findings),
    ]
    score = min(100, sum(points for points, _ in parts))
    level = next(name for limit, name in LEVELS if score >= limit)
    return {"score": score, "level": level, "reasons": [reason for _, reason in parts]}


def _profile(change, kb):
    device = kb.get_device(change["device"]) or {}
    return get_vendor(device.get("vendor"))


def _risky_devices(config, kb) -> set[str]:
    """Devices getting a "look twice" command (shutdown, ACL, removing things...)."""
    risky = set()
    for change in config:
        profile = _profile(change, kb)
        for command in change.get("commands", []):
            if profile and any(re.search(p, command.strip().lower()) for p, _ in profile.warn):
                risky.add(change["device"])
    return risky


def _severity(config, kb):
    best, why, extra = 0, "", 0
    for change in config:
        profile = _profile(change, kb)
        for command in change.get("commands", []):
            low = command.strip().lower()
            points, reason = 8, "adds configuration"
            if REMOVAL.search(low):
                points, reason = 15, "removes or changes existing configuration"
            if ROUTING.match(low):
                points, reason = 18, "changes routing"
            for pattern, text in (profile.warn if profile else []):
                if re.search(pattern, low):
                    extra += 1
                    points, reason = 22, text
            for pattern, text in (profile.blocked if profile else []):
                if re.search(pattern, low):
                    points, reason = 30, f"is a blocked command ({text})"
            if points > best:
                best, why = points, f"'{command}' on {change['device']} {reason}"
    points = min(30, best + 4 * max(0, extra - 1))
    more = f" (+{extra - 1} more risky command(s))" if extra > 1 else ""
    return points, f"Command severity {points}/30: {why}{more}."


def _criticality(config, graph, spof, harmless):
    best, why = 0, ""
    for name in dict.fromkeys(c["device"] for c in config):
        links = graph.degree(name) if name in graph else 0
        if name in spof:
            points, reason = 20, "is a single point of failure (the network splits without it)"
        elif links >= 3:
            points, reason = 12, f"is a hub ({links} links)"
        elif links == 2:
            points, reason = 6, "has 2 links"
        else:
            points, reason = 2, "is an edge device" if links else "has no known links"
        if points > best:
            best, why = points, f"{name} {reason}"
    if harmless:  # only adds configuration: a critical device is less of a worry
        best, why = best // 2, why + " (halved: the change only adds configuration)"
    return best, f"Device criticality {best}/20: {why}."


def _topology(config, graph, spof, risky, cut_access):
    best, why = 0, "the change does not touch links or traffic paths"
    for name in dict.fromkeys(c["device"] for c in config):
        links = graph.degree(name) if name in graph else 0
        if name in cut_access:
            points, reason = 15, f"the change touches the interface the system uses to reach {name}"
        elif name in risky and name in spof:
            points, reason = 15, f"a risky command on {name} could split the network"
        elif name in risky and links:
            points, reason = 7, f"a risky command on {name} could cut its links (there are backup paths)"
        else:
            continue
        if points > best:
            best, why = points, reason
    return best, f"Topology impact {best}/15: {why}."


def _affected(config, kb, spof, risky):
    total = max(1, len(kb.list_devices()))
    affected = set(c["device"] for c in config)
    cut_off = set()
    for name in risky & spof:
        groups = sorted(impact(kb, name), key=len)
        for group in groups[:-1]:  # every group except the biggest one loses contact
            cut_off.update(group)
    affected |= cut_off
    points = max(1, round(15 * len(affected) / total))
    extra = f", could cut off: {', '.join(sorted(cut_off))}" if cut_off else ""
    return points, (f"Affected devices {points}/15: {len(affected)} of {total} devices "
                    f"(changed: {', '.join(sorted(set(c['device'] for c in config)))}{extra}).")


def _rollback(findings):
    if findings.get("missing_rollback"):
        return 10, f"Rollback 10/10: {findings['missing_rollback']} change(s) have no rollback at all."
    if findings.get("cut_access"):
        return 10, ("Rollback 10/10: the change can cut the connection to "
                    f"{', '.join(findings['cut_access'])}, so the rollback might not reach it.")
    if findings.get("rollback_errors"):
        return 10, "Rollback 10/10: the rollback has errors (see the messages above)."
    if findings.get("rollback_warnings"):
        return 6, "Rollback 6/10: the rollback does not fully undo the change (see the warnings)."
    return 0, "Rollback 0/10: every change has a rollback that undoes it."


def _conflicts(findings):
    points, why = 0, []
    if findings.get("conflict_errors"):
        points += 10
        why.append(f"{findings['conflict_errors']} conflict error(s)")
    elif findings.get("conflict_warnings"):
        points += 5
        why.append(f"{findings['conflict_warnings']} possible conflict(s)")
    if findings.get("batfish_errors"):
        points += 10
        why.append(f"Batfish found {findings['batfish_errors']} problem(s)")
    elif findings.get("batfish_warnings"):
        points += 3
        why.append(f"Batfish gave {findings['batfish_warnings']} warning(s)")
    if findings.get("dependency_warnings") or findings.get("dependency_errors"):
        count = findings.get("dependency_warnings", 0) + findings.get("dependency_errors", 0)
        points += min(5, 3 * count)
        why.append(f"{count} missing prerequisite(s)")
    points = min(10, points)
    return points, f"Conflicts & prerequisites {points}/10: " + (", ".join(why) or "none found") + "."
