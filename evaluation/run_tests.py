"""Test the AI with a fixed list of requests and score every plan automatically.

    python evaluation/run_tests.py                 # every test, RAG off and on
    python evaluation/run_tests.py --rag on        # only with RAG
    python evaluation/run_tests.py --only route-1 dhcp

It uses YOUR AI settings from .env (LLM_PROVIDER, OLLAMA_MODEL...), the fixed test network in
evaluation/lab.json (not your devices) and the requests in evaluation/tests.json.
Nothing is sent to any device. Results: printed + saved in data/evaluation/<time>_<model>.csv

Marks:
    PASS  every required command is there, nothing forbidden, validation OK, rollback present
    HALF  the right commands, but a smaller problem (validation errors, no rollback, config in a check)
    FAIL  required commands missing, a forbidden command, no plan when one was needed, or an error
"""
import argparse
import csv
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


def summary(rows: list[dict]) -> str:
    lines = []
    for rag in dict.fromkeys(r["rag"] for r in rows):
        mine = [r for r in rows if r["rag"] == rag]
        count = {m: sum(r["mark"] == m for r in mine) for m in ("PASS", "HALF", "FAIL")}
        times = [r["seconds"] for r in mine if isinstance(r["seconds"], (int, float))]
        average = f"{sum(times) / len(times):.1f}s" if times else "-"
        lines.append(f"RAG {rag:3}: {count['PASS']}/{len(mine)} PASS, {count['HALF']} HALF, "
                     f"{count['FAIL']} FAIL, average {average} per plan")
    return "\n".join(lines)


def save(rows: list[dict], folder="data/evaluation") -> str:
    name = re.sub(r"[^\w.-]+", "-", plan_log.model_name())
    path = os.path.join(folder, f"{datetime.now():%Y-%m-%d_%H%M}_{name}.csv")
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows Arabic
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


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
    print(f"Saved: {save(rows)}")


if __name__ == "__main__":
    main()
