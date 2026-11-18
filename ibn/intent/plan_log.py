"""Save every plan the AI makes, so results are kept:
    data/plans.csv    one row per plan (PLAN_LOG in .env; empty = don't save)
    data/plans.html   the same, as a clear page to open in the browser (newest plan first)

Columns: time, model, rag, request, devices, commands, validation, errors, warnings, attempts, seconds
"""
import csv
import html
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
    write_page(settings.PLAN_LOG)


def write_page(csv_path: str) -> None:
    """data/plans.csv -> data/plans.html: a table with the newest plan first."""
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))[::-1]
    e = html.escape
    lines = "".join(
        f'<tr><td>{e(r["time"].replace("T", " "))}</td><td>{e(r["model"])}</td><td>{e(r["rag"])}</td>'
        f'<td dir="auto">{e(r["request"])}</td><td><pre>{e(r["commands"]) or "(no plan)"}</pre></td>'
        f'<td class="{e(r["validation"])}">{e(r["validation"])}</td><td><pre>{e(r["errors"])}</pre></td>'
        f'<td>{e(r["seconds"])}</td></tr>' for r in rows)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Plans</title><style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #fafafa; color: #222; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; font-size: 14px; }}
th {{ background: #f0f0f0; }} pre {{ margin: 0; white-space: pre-wrap; font-size: 13px; direction: ltr; }}
.ok {{ background: #d9f2df; color: #146c2e; font-weight: 600; }} .errors {{ background: #fadbd8; color: #9b1c12; font-weight: 600; }}
[dir=auto] {{ unicode-bidi: plaintext; }}
</style></head><body><h1>Every plan the AI made ({len(rows)})</h1>
<table><tr><th>Time</th><th>Model</th><th>RAG</th><th>Request</th><th>Plan (device (type): commands)</th>
<th>Validation</th><th>Errors</th><th>Seconds</th></tr>{lines}</table></body></html>"""
    with open(os.path.splitext(csv_path)[0] + ".html", "w", encoding="utf-8") as f:
        f.write(page)
