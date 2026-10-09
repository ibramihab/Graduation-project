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


def propose(text: str, kb, llm) -> dict:
    """Steps 1-3: understand the request and check it. Nothing is changed yet."""
    plan = translate(text, kb.list_devices(), llm)
    plan["validation"] = validate(plan, kb)
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
