"""The pipeline: connects the layers in order.

    text --> intent (AI) --> validation --> [user approves] --> control --> devices

The web page only calls these two functions, so a different interface
(a chat bot, a command line tool, ...) can reuse them without changes.
"""
import uuid

from .control import apply_plan
from .intent import translate
from .validation import validate

PENDING: dict[str, dict] = {}  # plans waiting for the user to approve them
ATTEMPTS = 2  # if validation finds mistakes, the AI gets one more try to fix them


def propose(text: str, kb, llm) -> dict:
    """Steps 1-3: understand the request and check it. Nothing is changed yet."""
    request = text
    for attempt in range(1, ATTEMPTS + 1):
        plan = translate(request, kb.list_devices(), llm, kb.list_links())
        plan["validation"] = validate(plan, kb)
        if plan["validation"]["ok"] or not plan["changes"]:
            break
        # Tell the AI what was wrong and let it try again.
        request = (text + "\n\nYour previous plan was rejected by the safety checks:\n- "
                   + "\n- ".join(plan["validation"]["errors"]) + "\nFix these problems.")
    plan["intent"] = text
    plan["attempts"] = attempt
    plan["id"] = uuid.uuid4().hex[:8]
    if plan["validation"]["ok"]:
        PENDING[plan["id"]] = plan
    return plan


def approve(plan_id: str, kb) -> dict:
    """Step 4: the user said yes, apply it."""
    plan = PENDING.pop(plan_id, None)
    if not plan:
        return {"success": False, "results": [], "error": "Unknown or already used plan id"}
    # Check again: the network may have changed since the plan was made.
    check = validate(plan, kb)
    if not check["ok"]:
        return {"success": False, "results": [], "error": "; ".join(check["errors"])}
    return apply_plan(plan, kb)
