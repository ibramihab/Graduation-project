"""Test the web-page router driver (browser agent) against a fake router website.

A scripted "AI" picks actions with simple rules, so this tests the browser side
(login, menus, frames, typing, Save) without needing a real LLM.
Skipped when no browser is installed (run: python -m playwright install chromium).
"""
import re
import threading

import pytest

import ibn.intent
from ibn import settings
from ibn.infrastructure.drivers import get_driver

from .fake_router import STATE, app

URL = "http://127.0.0.1:5077/"
DEVICE = {"name": "HomeRouter", "ip": "127.0.0.1", "vendor": "web_gui", "url": URL,
          "username": "admin", "password": "S3cret!"}


class ScriptedAI:
    """Acts like the LLM: reads the numbered ELEMENTS and returns the next action."""

    def __init__(self):
        self.prompts = []

    def ask_json(self, system, user, schema):
        self.prompts.append(user)
        elements = user.split("ELEMENTS:\n")[1].splitlines()
        has = lambda pattern: any(re.search(pattern, e) for e in elements)
        number = lambda pattern: next(int(re.match(r"\[(\d+)\]", e)[1]) for e in elements if re.search(pattern, e))
        act = lambda a, n=-1, v="", answer="": {"action": a, "element": n, "value": v, "reason": "", "answer": answer}
        new_name = re.search(r"to (\S+)\n", user)
        if has(r'label="Username" value=""'):
            return act("fill", number("Username"), "{username}")
        if has(r'type=password.*value=""'):
            return act("fill", number("type=password"), "{password}")
        if has(r'"Login"'):
            return act("click", number('"Login"'))
        if has(r"id=ESSID"):
            if "READ-ONLY" in system:
                return act("done", answer=re.search(r'id=ESSID> label="[^"]*" value="([^"]*)"', user)[1])
            if f'value="{new_name[1]}"' not in user:
                return act("fill", number("id=ESSID"), new_name[1])
            if "Saved successfully" not in user:
                return act("click", number('"Apply"'))
            return act("done", answer="saved")
        if has(r'"WLAN"'):
            return act("click", number('"WLAN"'))
        return act("click", number('"Local Network"'))


@pytest.fixture(scope="module", autouse=True)
def router():
    threading.Thread(target=lambda: app.run(port=5077), daemon=True).start()


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_BROWSER", False)
    scripted = ScriptedAI()
    monkeypatch.setattr(ibn.intent, "get_llm", lambda: scripted)
    STATE.update(ssid="Orange-1234", wifi_password="wifi-pass-123", logged_in=False)
    try:
        get_driver(DEVICE).__enter__().disconnect()
    except Exception as e:
        pytest.skip(f"no browser available: {e}")
    STATE["logged_in"] = False
    return scripted


def test_change_wifi_name(ai):
    with get_driver(DEVICE) as driver:
        driver.send_config(["Change the Wi-Fi network name (SSID) to Home5G"])
    assert STATE["ssid"] == "Home5G"
    assert "Username" not in ai.prompts[0]  # logged in without the AI
    # the Wi-Fi page also has a password box: the router password must NOT be typed into it
    assert STATE["wifi_password"] == "wifi-pass-123"
    assert not any("S3cret!" in p for p in ai.prompts)  # the AI never sees the password


def test_read_only_task_reads_without_changing(ai):
    with get_driver(DEVICE) as driver:
        output = driver.run_commands(["Read the current Wi-Fi network name"])
    assert output.endswith("Orange-1234")
    assert STATE["ssid"] == "Orange-1234"


def test_wrong_password_gives_a_clear_error(ai):
    with pytest.raises(RuntimeError, match="Login failed"):
        with get_driver({**DEVICE, "password": "wrong"}):
            pass
    assert ai.prompts == []  # logging in never needs the AI
