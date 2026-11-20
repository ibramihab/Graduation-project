"""Control layer: applies an approved plan, and undoes it if anything fails.

For each step in the plan:
  "config" step:
    1. connect (driver picked by vendor)
    2. save a backup of the current config in the knowledge base
    3. send the commands (configuration mode)
  "check" step (ping, show...):
    run the commands in normal mode and show the output. Nothing to undo.
If ANY config step fails, we run the rollback commands on every device we already
changed (newest first), so the network goes back to how it was.
A failed check (e.g. we could not log in) is reported but does not undo anything.

Post-validation: when every config step worked, we run each step's "verify" commands
(ping, show...) to check the intent REALLY happened. If one fails (e.g. the ping gets
no reply), the intent was not reached, so we roll everything back, like any failure.
Everything is written to the device's history in the knowledge base.
"""
import re
from datetime import datetime

from .. import settings
from ..infrastructure.drivers import get_driver
from ..vendors import get_vendor


def apply_plan(plan: dict, kb) -> dict:
    done = []      # changes that worked so far (needed for rollback)
    results = []

    for change in plan["changes"]:
        device = kb.get_device(change["device"])
        if change.get("type") == "check":
            results.append(_check(device, change))
            continue
        try:
            if settings.DRY_RUN:
                output = "DRY RUN - nothing was sent:\n" + "\n".join(change["commands"])
            else:
                with get_driver(device) as driver:
                    kb.save_backup(device["name"], driver.get_config())
                    output = driver.send_config(change["commands"])
            done.append(change)
            results.append({"device": device["name"], "status": "applied", "output": output})
        except Exception as error:
            results.append({"device": device["name"], "status": "failed", "output": str(error)})
            # The failed device may have taken some commands before the error, so undo it too.
            results += _rollback(done + [change], kb)
            _record(plan, results, kb, success=False)
            return {"success": False, "results": results}

    # Post-validation: every config step worked, now check the intent really happened.
    checks = _verify(done, kb)
    results += checks
    if any(r["status"] == "verify failed" for r in checks):
        results += _rollback(done, kb)
        _record(plan, results, kb, success=False)
        return {"success": False, "results": results}

    # A failed check (e.g. a ping that couldn't run) doesn't undo anything,
    # but the result must still say "Failed", not "Done!".
    success = not any(r["status"] == "check failed" for r in results)
    _record(plan, results, kb, success=success)
    return {"success": success, "results": results}


def _check(device: dict, change: dict) -> dict:
    try:
        if settings.DRY_RUN:
            output = "DRY RUN - nothing was sent:\n" + "\n".join(change["commands"])
        else:
            with get_driver(device) as driver:
                output = driver.run_commands(change["commands"])
        return {"device": device["name"], "status": "checked", "output": output}
    except Exception as error:
        return {"device": device["name"], "status": "check failed", "output": str(error)}


def _verify(changes: list[dict], kb) -> list[dict]:
    """Run the "verify" commands of the applied steps. Status "verified" or "verify failed"."""
    results = []
    for change in changes:
        if not change.get("verify"):
            continue
        device = kb.get_device(change["device"])
        if settings.DRY_RUN:
            results.append({"device": device["name"], "status": "verify skipped (dry run)",
                            "output": "\n".join(change["verify"])})
            continue
        try:
            with get_driver(device) as driver:
                output = driver.run_commands(change["verify"])
            failed = _looks_failed(output, device)
        except Exception as error:  # we could not even run the check
            output, failed = str(error), True
        results.append({"device": device["name"], "output": output,
                        "status": "verify failed" if failed else "verified"})
    return results


def _looks_failed(output: str, device: dict) -> bool:
    """True if the output shows the check failed: a ping with no reply
    (the vendor's verify_failed) or a rejected command (its error_markers)."""
    profile = get_vendor(device.get("vendor"))
    if not profile:
        return False
    text = output.lower()
    return (any(re.search(pattern, text) for pattern in profile.verify_failed)
            or any(marker.lower() in text for marker in profile.error_markers))


def _rollback(changes: list[dict], kb) -> list[dict]:
    results = []
    for change in reversed(changes):
        device = kb.get_device(change["device"])
        if not change.get("rollback") or settings.DRY_RUN:
            continue
        try:
            with get_driver(device) as driver:
                output = driver.send_config(change["rollback"])
            results.append({"device": device["name"], "status": "rolled back", "output": output})
        except Exception as error:
            results.append({"device": device["name"], "status": "ROLLBACK FAILED - check by hand",
                            "output": str(error)})
    return results


def _record(plan: dict, results: list[dict], kb, success: bool) -> None:
    time = datetime.now().isoformat(timespec="seconds")
    for change in plan["changes"]:
        kb.record_change(change["device"], {
            "time": time,
            "intent": plan.get("intent", ""),
            "type": change.get("type", "config"),
            "commands": change["commands"],
            "success": success,
            "results": [r for r in results if r["device"] == change["device"]],
        })
