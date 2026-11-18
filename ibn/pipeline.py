"""The pipeline: connects the layers in order.

    text --> intent (AI) --> validation --> [user approves] --> control --> devices

The web page only calls these two functions, so a different interface
(a chat bot, a command line tool, ...) can reuse them without changes.
"""
import uuid

from .control import apply_plan
from .intent import translate
from .validation import validate
from .validation.validator import request_problems

PENDING: dict[str, dict] = {}  # plans waiting for the user to approve them
ATTEMPTS = 2  # if validation finds mistakes, the AI gets one more try to fix them

# Sent with the errors on the second try. Without it, a small AI "fixes" a wrong request by
# guessing (the user asked for VLANs 20-5000, it quietly made it 20-500).
NO_GUESSING = (
    "Fix only the mistakes YOU made (wrong command, wrong interface name...).\n"
    "If the problem is in the user's request itself (for example a number outside the "
    "allowed range), do NOT change or guess the user's values: return no changes, and in "
    "\"summary\" say why it can't be done and the rule it breaks (for example \"VLANs must be "
    "1-4094\"). Do NOT suggest a different value to use instead: the user decides that."
)


def propose(text: str, kb, llm) -> dict:
    """Steps 1-3: understand the request and check it. Nothing is changed yet."""
    request = text
    for attempt in range(1, ATTEMPTS + 1):
        plan = translate(request, kb.list_devices(), llm, kb.list_links())
        plan["validation"] = validate(plan, kb)
        # Stop when it passed, when the AI made no plan, or when the user's own request is wrong
        # (asking the AI again can't fix the request, and a small AI would only guess a new value).
        if plan["validation"]["ok"] or not plan["changes"] or request_problems(text):
            break
        # Tell the AI what was wrong and let it try again.
        request = (text + "\n\nYour previous plan was rejected by the safety checks:\n- "
                   + "\n- ".join(plan["validation"]["errors"]) + "\n" + NO_GUESSING)
    plan["intent"] = text
    plan["attempts"] = attempt
    problems = request_problems(text)
    if problems:  # say it in our words, and hide the AI's plan: nothing it made up is shown
        plan["summary"] = "This can't be done. " + " ".join(problems)
        plan["changes"] = []
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
