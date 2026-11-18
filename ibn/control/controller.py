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
Everything is written to the device's history in the knowledge base.

Changing a device's management IP (the IP we use to reach it): our SSH session drops in
the middle, which is expected. So instead of calling it a failure, we ping the new IP.
If the device answers there, the change worked and the knowledge base gets the new IP.
"""
from datetime import datetime

from .. import settings
from ..infrastructure.discovery import ping
from ..infrastructure.drivers import get_driver
from ..validation.validator import management_interface, new_management_ip


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
                output = _send(device, change, kb)
            done.append(change)
            results.append({"device": device["name"], "status": "applied", "output": output})
        except Exception as error:
            results.append({"device": device["name"], "status": "failed", "output": str(error)})
            # The failed device may have taken some commands before the error, so undo it too.
            results += _rollback(done + [change], kb)
            _record(plan, results, kb, success=False)
            return {"success": False, "results": results}

    # A failed check (e.g. a ping that couldn't run) doesn't undo anything,
    # but the result must still say "Failed", not "Done!".
    success = not any(r["status"] == "check failed" for r in results)
    _record(plan, results, kb, success=success)
    return {"success": success, "results": results}


def _send(device: dict, change: dict, kb) -> str:
    """Back up the config, send the commands. Follows the device if they change its management IP."""
    moving_to = new_management_ip(device, change["commands"])  # e.g. ("10.0.1.50", 24) or None
    try:
        with get_driver(device) as driver:
            kb.save_backup(device["name"], driver.get_config())
            output = driver.send_config(change["commands"])
    except Exception:
        # Losing the connection is expected when we change the IP we are connected to.
        if not (moving_to and ping(moving_to[0])):
            raise  # a real failure: the caller rolls back
        output = "The connection dropped while changing the management IP (expected)."
    if moving_to:
        _move_device(device, *moving_to, kb)
        output += f"\n{device['name']} is now reached on {moving_to[0]} (saved in the program)."
    return output


def _move_device(device: dict, ip: str, prefix: int, kb) -> None:
    """Save the new management IP, and update the management interface's line too."""
    interface = management_interface(device)
    interfaces = [f"{interface} {ip}/{prefix}" if i.split()[0] == interface else i
                  for i in device.get("interfaces") or []]
    kb.update_device(device["name"], ip=ip, interfaces=interfaces)


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
