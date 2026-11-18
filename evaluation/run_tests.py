"""Test the AI with a fixed list of requests and score every plan automatically.

    python evaluation/run_tests.py                 # every test, RAG off and on
    python evaluation/run_tests.py --rag on        # only with RAG
    python evaluation/run_tests.py --only route-1 dhcp

It uses YOUR AI settings from .env (LLM_PROVIDER, OLLAMA_MODEL...), the fixed test network in
evaluation/lab.json (not your devices) and the requests in evaluation/tests.json.
Nothing is sent to any device. Results: printed + saved in data/evaluation/<time>_<model>.html
(open it in the browser: a clear colored table) and .csv (the same data for Excel).

Marks:
    PASS  every required command is there, nothing forbidden, validation OK, rollback present
    HALF  the right commands, but a smaller problem (validation errors, no rollback, config in a check)
    FAIL  required commands missing, a forbidden command, no plan when one was needed, or an error
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so "import ibn" works when run from anywhere

from ibn import pipeline, settings  # noqa: E402
from ibn.intent import get_llm, plan_log  # noqa: E402
from ibn.knowledge.file_graph import FileGraph  # noqa: E402

COLUMNS = ["rag", "id", "feature", "request", "mark", "seconds", "attempts", "problems", "plan"]


def load_lab(path=HERE / "lab.json"):
    """The test network in a temporary knowledge base (your real data/ is never touched)."""
    lab = json.loads(Path(path).read_text(encoding="utf-8"))
    kb = FileGraph(os.path.join(tempfile.mkdtemp(), "lab.json"))
    for device in lab["devices"]:
        kb.add_device(device)
    for a, b in lab["links"]:
        kb.add_link(a, b)
    return kb


def load_tests(path=HERE / "tests.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def norm(text: str) -> str:
    """Lower case, single spaces: "Ip  Route 1.1.1.0" == "ip route 1.1.1.0"."""
    return re.sub(r"\s+", " ", text.strip().lower())


def score(test: dict, plan: dict) -> tuple[str, list[str]]:
    """-> ("PASS" / "HALF" / "FAIL", [the problems found])"""
    changes = plan.get("changes", [])
    validation = plan.get("validation", {})
    if test["kind"] == "refuse":
        if not changes or not validation.get("ok"):
            return "PASS", []
        return "FAIL", ["made a plan that passed validation, but this request must be refused"]
    if not changes:
        return "FAIL", ["no plan: " + plan.get("summary", "")[:120]]

    commands_of = {}  # device -> all its commands, one per line
    for change in changes:
        commands_of.setdefault(change["device"], []).extend(norm(c) for c in change["commands"])
    every_command = "\n".join(c for lines in commands_of.values() for c in lines)

    big, small = [], []
    for device, needed in test.get("must", {}).items():
        if device != "*" and device not in commands_of:
            big.append(f"{device} is not in the plan")
            continue
        where = every_command if device == "*" else "\n".join(commands_of[device])
        big += [f"missing on {device}: {n}" for n in needed if norm(n) not in where]
    big += [f"should not contain: {bad}" for bad in test.get("must_not", []) if norm(bad) in every_command]

    if not validation.get("ok"):
        small.append("validation errors: " + "; ".join(validation.get("errors", []))[:200])
    if test["kind"] == "check" and any(c.get("type") == "config" for c in changes):
        small.append("changes the configuration for a check request")
    if any(c.get("type") == "config" and not c.get("rollback") for c in changes):
        small.append("a config step has no rollback")
    return ("FAIL" if big else "HALF" if small else "PASS"), big + small


def run(tests: list[dict], llm, rag_modes: list[bool], show=print) -> list[dict]:
    """Make a plan for every test (with each RAG mode) and score it. -> one row per test and mode."""
    rows = []
    for rag in rag_modes:
        settings.RAG_ENABLED = rag
        show(f"\n=== RAG {'on' if rag else 'off'} ===")
        for test in tests:
            kb = load_lab()
            try:
                plan = pipeline.propose(test["request"], kb, llm)
                mark, problems = score(test, plan)
            except requests.exceptions.ConnectionError:
                show("STOP: can't reach the AI. Is Ollama running (ollama ps)? Check OLLAMA_URL in .env.")
                return rows
            except Exception as error:  # any other problem: count it as a failed plan and go on
                plan, mark, problems = {}, "FAIL", [f"error: {error}"]
            row = {"rag": "on" if rag else "off", "id": test["id"], "feature": test.get("feature", ""),
                   "request": test["request"], "mark": mark, "seconds": plan.get("seconds", ""),
                   "attempts": plan.get("attempts", ""), "problems": "\n".join(problems),
                   "plan": "\n".join(f'{c["device"]}: ' + " | ".join(c["commands"]) for c in plan.get("changes", []))}
            rows.append(row)
            show(f'{mark:4}  {row["seconds"]!s:>5}s  {test["id"]:16} {problems[0] if problems else ""}')
    return rows


def totals(rows: list[dict]) -> list[dict]:
    """Per RAG mode: how many PASS / HALF / FAIL and the average seconds."""
    result = []
    for rag in dict.fromkeys(r["rag"] for r in rows):
        mine = [r for r in rows if r["rag"] == rag]
        times = [r["seconds"] for r in mine if isinstance(r["seconds"], (int, float))]
        result.append({"rag": rag, "total": len(mine), **{m: sum(r["mark"] == m for r in mine) for m in ("PASS", "HALF", "FAIL")},
                       "average": f"{sum(times) / len(times):.1f}s" if times else "-"})
    return result


def summary(rows: list[dict]) -> str:
    return "\n".join(f"RAG {t['rag']:3}: {t['PASS']}/{t['total']} PASS, {t['HALF']} HALF, {t['FAIL']} FAIL, "
                     f"average {t['average']} per plan" for t in totals(rows))


def save(rows: list[dict], folder="data/evaluation") -> str:
    """Save the results twice: .html (to read in the browser) and .csv (for Excel). -> the .html path"""
    name = re.sub(r"[^\w.-]+", "-", plan_log.model_name())
    base = os.path.join(folder, f"{datetime.now():%Y-%m-%d_%H%M}_{name}")
    os.makedirs(folder, exist_ok=True)
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Arabic
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(report(rows))
    return base + ".html"


# ---------- the HTML report ----------
STYLE = """
body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; background: #fafafa; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 28px 0 8px; }
.sub { color: #666; margin-bottom: 18px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px; min-width: 220px; }
.card b { font-size: 26px; }
table { border-collapse: collapse; width: 100%; background: #fff; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; font-size: 14px; }
th { background: #f0f0f0; }
.PASS { background: #d9f2df; color: #146c2e; font-weight: 600; text-align: center; }
.HALF { background: #fff1c2; color: #7a5b00; font-weight: 600; text-align: center; }
.FAIL { background: #fadbd8; color: #9b1c12; font-weight: 600; text-align: center; }
pre { margin: 0; white-space: pre-wrap; font-size: 13px; direction: ltr; }
[dir=auto] { unicode-bidi: plaintext; }
"""


def report(rows: list[dict]) -> str:
    """A self-contained web page: summary per RAG mode, side-by-side marks, then every plan."""
    e = html.escape
    modes = list(dict.fromkeys(r["rag"] for r in rows))
    cards = "".join(f'<div class="card">RAG {e(t["rag"])}<br><b>{t["PASS"]}/{t["total"]} PASS</b><br>'
                    f'{t["HALF"]} HALF, {t["FAIL"]} FAIL, average {t["average"]} per plan</div>' for t in totals(rows))
    marks = {(r["id"], r["rag"]): r for r in rows}
    compare = "".join(
        f'<tr><td>{e(t["id"])}</td><td>{e(t["feature"])}</td><td dir="auto">{e(t["request"])}</td>'
        + "".join(f'<td class="{marks[(t["id"], m)]["mark"]}">{marks[(t["id"], m)]["mark"]}</td>'
                  f'<td>{marks[(t["id"], m)]["seconds"]}</td>' if (t["id"], m) in marks else "<td></td><td></td>"
                  for m in modes) + "</tr>"
        for t in {r["id"]: r for r in rows}.values())
    details = "".join(
        f'<tr><td>{e(r["rag"])}</td><td>{e(r["id"])}</td><td class="{r["mark"]}">{r["mark"]}</td>'
        f'<td dir="auto">{e(r["request"])}</td><td><pre>{e(r["plan"]) or "(no plan)"}</pre></td>'
        f'<td><pre>{e(r["problems"])}</pre></td></tr>' for r in rows)
    head = "".join(f"<th>RAG {e(m)}</th><th>seconds</th>" for m in modes)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>AI test results</title>
<style>{STYLE}</style></head><body>
<h1>AI test results</h1>
<div class="sub">Model: {e(plan_log.model_name())} &middot; {datetime.now():%Y-%m-%d %H:%M} &middot; {len(marks)} plans</div>
<div class="cards">{cards}</div>
<h2>Side by side</h2>
<table><tr><th>Test</th><th>Feature</th><th>Request</th>{head}</tr>{compare}</table>
<h2>Every plan</h2>
<table><tr><th>RAG</th><th>Test</th><th>Mark</th><th>Request</th><th>Plan (device: commands)</th><th>Problems</th></tr>{details}</table>
<p class="sub">PASS = all required commands, validation OK, rollback present &middot; HALF = right commands, smaller problem
&middot; FAIL = commands missing or wrong, no plan, or an error</p>
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="Score the AI's plans on a fixed list of requests.")
    parser.add_argument("--rag", choices=["on", "off", "both"], default="both")
    parser.add_argument("--only", nargs="*", help="test ids to run (default: all)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console + Arabic

    tests = [t for t in load_tests() if not args.only or t["id"] in args.only]
    rag_modes = {"on": [True], "off": [False], "both": [False, True]}[args.rag]
    settings.PLAN_LOG = ""  # this command saves its own results file
    print(f"Model: {plan_log.model_name()}   Tests: {len(tests)}   Nothing is sent to devices.")
    rows = run(tests, get_llm(), rag_modes)
    if not rows:
        return  # nothing ran (the AI couldn't be reached): no results file
    print("\n" + summary(rows))
    print(f"Report (open in the browser): {save(rows)}")


if __name__ == "__main__":
    main()
