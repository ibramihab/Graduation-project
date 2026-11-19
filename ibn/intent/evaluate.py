"""Exam for the Intent layer: how good is the AI, phase by phase?

    python -m ibn.intent.evaluate              all phases
    python -m ibn.intent.evaluate --phase 1    only phase 1

It uses the AI from your .env (Claude or Ollama), so it needs a working AI.
Nothing is sent to any device: each request only goes through translate + validate,
on a copy of the lab network written in tests/intents.json (not your saved devices).

Each case in tests/intents.json has a request and what we expect:
    "devices":  the plan must use exactly these devices
    "commands": each text must appear in one of the commands (capitals/spaces ignored)
    "type":     every step must be this type ("config" or "check")
    "verify":   true = every config step must have post-validation commands
    "question": true = the request misses information: the AI must ASK, not guess
    "rejected": true = negative test: the system must refuse it (no plan that passes)
A case passes when the plan matches everything it expects.
"""
import argparse
import json
import os
import tempfile

from .. import pipeline
from ..knowledge.file_graph import FileGraph
from .llm import get_llm

CASES_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "intents.json")


def load_exam(path: str = CASES_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_kb(topology: dict, folder: str) -> FileGraph:
    """A throw-away knowledge base with the exam's devices and links."""
    kb = FileGraph(os.path.join(folder, "exam.json"))
    for device in topology["devices"]:
        kb.add_device(dict(device))
    for a, b in topology["links"]:
        kb.add_link(a, b)
    return kb


def _same(text: str) -> str:
    """Compare commands ignoring capitals and extra spaces."""
    return " ".join(text.lower().split())


def problems(plan: dict, expect: dict) -> list[str]:
    """What is wrong with the AI's plan for this case. [] = passed."""
    changes = plan.get("changes", [])
    ok = plan.get("validation", {}).get("ok", False)

    if expect.get("rejected"):
        return [] if (not changes or not ok) else ["should have been refused, but the plan passed"]
    if expect.get("question"):
        return [] if plan.get("question") else ["should have asked a question (information is missing)"]

    found = []
    if plan.get("question"):
        return [f"asked a question instead of planning: {plan['question']}"]
    if not ok:
        found.append("failed validation: " + "; ".join(plan.get("validation", {}).get("errors", [])))
    if "devices" in expect and {c["device"] for c in changes} != set(expect["devices"]):
        found.append(f"devices {sorted({c['device'] for c in changes})}, expected {sorted(expect['devices'])}")
    every_command = [_same(cmd) for c in changes for cmd in c.get("commands", [])]
    for wanted in expect.get("commands", []):
        if not any(_same(wanted) in cmd for cmd in every_command):
            found.append(f"missing command '{wanted}'")
    if "type" in expect and any(c.get("type") != expect["type"] for c in changes):
        found.append(f"every step should be type '{expect['type']}'")
    if expect.get("verify") and any(c.get("type") == "config" and not c.get("verify") for c in changes):
        found.append("a config step has no verify (post-validation) commands")
    return found


def run_exam(llm, exam: dict, phase: int | None = None) -> list[dict]:
    """Ask the AI every case and score it. Returns one result per case."""
    results = []
    with tempfile.TemporaryDirectory() as folder:
        kb = build_kb(exam["topology"], folder)
        for case in exam["cases"]:
            if phase and case["phase"] != phase:
                continue
            try:
                plan = pipeline.propose(case["request"], kb, llm)
                found = problems(plan, case["expect"])
            except Exception as error:  # the AI did not answer (e.g. Ollama error 500)
                plan, found = {}, [f"the AI did not answer: {error}"]
            pipeline.PENDING.pop(plan.get("id"), None)  # never approved, don't keep it
            results.append({"phase": case["phase"], "request": case["request"],
                            "passed": not found, "problems": found})
    return results


def scores(results: list[dict]) -> dict:
    """{phase: (passed, total)}"""
    table = {}
    for r in results:
        passed, total = table.get(r["phase"], (0, 0))
        table[r["phase"]] = (passed + r["passed"], total + 1)
    return dict(sorted(table.items()))


def main():
    parser = argparse.ArgumentParser(description="Score the AI on tests/intents.json")
    parser.add_argument("--phase", type=int, help="only this phase (1, 2 or 3)")
    args = parser.parse_args()

    results = run_exam(get_llm(), load_exam(), args.phase)
    for r in results:
        print(("PASS" if r["passed"] else "FAIL"), f"[phase {r['phase']}]", r["request"])
        for problem in r["problems"]:
            print("      -", problem)
    print()
    total_passed = total = 0
    for phase, (passed, count) in scores(results).items():
        print(f"Phase {phase}: {passed}/{count}  ({100 * passed // count}%)")
        total_passed, total = total_passed + passed, total + count
    if total:
        print(f"Total:   {total_passed}/{total}  ({100 * total_passed // total}%)")


if __name__ == "__main__":
    main()
