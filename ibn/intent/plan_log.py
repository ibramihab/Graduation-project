"""Save every plan the AI makes as one row of a CSV file (opens in Excel), so results are kept:
    data/plans.csv   (PLAN_LOG in .env; empty = don't save)

Columns: time, model, rag, request, devices, commands, validation, errors, warnings, attempts, seconds
"""
import csv
import os
from datetime import datetime

from .. import settings

COLUMNS = ["time", "model", "rag", "request", "devices", "commands", "validation",
           "errors", "warnings", "attempts", "seconds"]


def model_name() -> str:
    """Which AI made the plan, e.g. "ollama:qwen3.5:4b"."""
    if settings.LLM_PROVIDER == "ollama":
        return f"ollama:{settings.OLLAMA_MODEL}"
    return f"{settings.LLM_PROVIDER}:{settings.CLAUDE_MODEL}"


def save(plan: dict) -> None:
    if not settings.PLAN_LOG:
        return
    validation = plan.get("validation", {})
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model_name(),
        "rag": "on" if settings.RAG_ENABLED else "off",
        "request": plan.get("intent", ""),
        "devices": " ".join(dict.fromkeys(c["device"] for c in plan.get("changes", []))),
        # one line per step: "R1 (config): ip route ... | no ..."
        "commands": "\n".join(f'{c["device"]} ({c.get("type", "config")}): ' + " | ".join(c["commands"])
                              for c in plan.get("changes", [])),
        "validation": "ok" if validation.get("ok") else "errors",
        "errors": "\n".join(validation.get("errors", [])),
        "warnings": "\n".join(validation.get("warnings", [])),
        "attempts": plan.get("attempts", 1),
        "seconds": plan.get("seconds", ""),
    }
    new_file = not os.path.exists(settings.PLAN_LOG)
    os.makedirs(os.path.dirname(settings.PLAN_LOG) or ".", exist_ok=True)
    # utf-8-sig: Excel then shows Arabic requests correctly
    with open(settings.PLAN_LOG, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
