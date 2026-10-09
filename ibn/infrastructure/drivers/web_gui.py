"""Home routers that only have a web page (no CLI): a small "browser agent".

How it works (works on almost any router brand, no per-router code):
  1. open the router's page in a real browser (Playwright), so JavaScript works,
     and log in (simple rules, no AI needed: find the password box, fill, click Login)
  2. list everything on the page you can type into or click, and number it:
        [3] <input type=text id=Frm_Username> label="Username" value=""
        [7] <button> "Login"
  3. ask the AI: "the task is X, here is the page, what is the NEXT action?"
        -> {"action": "fill", "element": 3, "value": "{username}"}
  4. do that action, read the page again, repeat until the AI says "done"

Commands for this driver are plain English, e.g. "Change the Wi-Fi name to Home5G".
The AI never sees the router password: it writes "{password}" and we put in the real one.
Set SHOW_BROWSER=true in .env to watch it work in a browser window.
"""
import os
import re
import time

from playwright.sync_api import sync_playwright

from ... import settings
from .base import Driver

MAX_STEPS = 15      # give up after this many AI actions
TIME_LIMIT = 300    # ...or after 5 minutes (a local AI on a laptop is slow)
MAX_ELEMENTS = 80   # fewer elements = smaller, faster AI requests
MAX_TEXT = 800      # characters of page text shown to the AI

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["click", "fill", "select", "done", "fail"]},
        "element": {"type": "integer"},
        "value": {"type": "string"},
        "reason": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["action", "element", "value", "reason", "answer"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You control a web browser to manage a home router through its web page.
Each turn you get: the task, the actions you already did, and the current page (its text
and a numbered list of ELEMENTS you can use). Reply with ONE next action:
- "fill":   type "value" into text/password box number "element"
- "select": choose option "value" in drop-down number "element"
- "click":  click element number "element" (buttons, links, menus, tabs, checkboxes)
- "done":   the task is finished; write what you did or found in "answer"
- "fail":   the task is impossible; explain why in "answer"

Rules:
- You are already logged in. If you still see a login page, fill the username box with
  {username} and the password box with {password} (write these placeholders exactly).
- Find settings through the menus. Wi-Fi settings are usually under names like
  "Local Network", "WLAN", "Wireless", "Wi-Fi", then a sub-menu like "WLAN Basic" or
  "SSID Settings". Click menus and sub-menus until you see the right fields.
- Routers often have two Wi-Fi networks (2.4 GHz and 5 GHz, or SSID1/SSID2). Change the
  one the task names; if the task doesn't say, change SSID1 / the first one.
- After changing values, click the "Apply" / "Save" / "Submit" button of that section.
- Say "done" only after saving (or, for read-only tasks, when you can see the answer).
- Use element -1 for "done"/"fail". Use "" for "value" and "answer" when not needed.
- If an action didn't work, try something different. Don't repeat the same action.
"""

READ_ONLY_RULES = """
THIS IS A READ-ONLY TASK: only click menus, sub-menus and tabs to find the information. Never type anything else, never select, never click
Apply/Save/Reboot. Put the information in "answer".
"""

# Buttons a read-only task must never click.
CHANGING_WORDS = re.compile(r"apply|save|submit|reboot|restart|reset|delete|restore|upgrade", re.I)

# JavaScript that numbers the usable elements of a page (runs inside the browser).
LIST_ELEMENTS_JS = r"""
(start) => {
  const visible = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const ownText = el => [...el.childNodes].filter(n => n.nodeType === 3)
    .map(n => n.textContent.trim()).join(' ').trim();
  const clean = t => (t || '').trim().replace(/\s+/g, ' ').slice(0, 50);
  const label = el => {
    const l = (el.labels && el.labels[0] && el.labels[0].innerText) ||
      el.getAttribute('aria-label') || el.title || el.placeholder;
    if (l) return clean(l);
    const row = el.closest('tr, label, li, p');
    if (row) return clean(row.innerText);
    return clean(el.previousElementSibling && el.previousElementSibling.innerText);
  };
  document.querySelectorAll('[data-ibn]').forEach(e => e.removeAttribute('data-ibn'));
  const out = [];
  let i = start;
  for (const el of document.querySelectorAll('body *')) {
    if (out.length >= 150) break;
    const tag = el.tagName.toLowerCase();
    const isField = ['input', 'select', 'textarea', 'button', 'a'].includes(tag);
    // menus are often plain <div>/<span> with a mouse "hand" cursor
    const clickable = !isField && (el.hasAttribute('onclick') || el.getAttribute('role') === 'button' ||
      (getComputedStyle(el).cursor === 'pointer' && ownText(el)));
    if (!(isField || clickable) || !visible(el)) continue;
    if (tag === 'input' && el.type === 'hidden') continue;
    if (!isField && el.parentElement && el.parentElement.closest('a, button, [data-ibn]')) continue;
    el.setAttribute('data-ibn', i);
    let d = `[${i}] <${tag}`;
    if ((tag === 'input' || tag === 'select') && el.type) d += ` type=${el.type}`;
    if (el.name) d += ` name=${el.name}`;
    if (el.id) d += ` id=${el.id}`;
    d += '>';
    if (tag === 'input' || tag === 'textarea') {
      d += ` label="${label(el)}"`;
      if (el.type === 'checkbox' || el.type === 'radio') d += el.checked ? ' (checked)' : ' (not checked)';
      else if (el.type === 'password') d += el.value ? ' value=(hidden)' : ' value=""';
      else if (el.type !== 'button' && el.type !== 'submit') d += ` value="${clean(el.value)}"`;
      else d += ` "${clean(el.value)}"`;
    } else if (tag === 'select') {
      d += ` label="${label(el)}" selected="${clean(el.selectedOptions[0] && el.selectedOptions[0].text)}"` +
        ` options=[${[...el.options].slice(0, 10).map(o => clean(o.text)).join(', ')}]`;
    } else {
      d += ` "${clean(el.innerText || el.value || el.title)}"`;
    }
    out.push(d);
    i++;
  }
  return out;
}
"""


class WebGuiDriver(Driver):
    def connect(self):
        from ...intent import get_llm  # the AI that reads the page
        self.llm = get_llm()
        self.url = self.device.get("url") or f"http://{self.device['ip']}/"
        self.read_only = False
        self.playwright = sync_playwright().start()
        headless = not settings.SHOW_BROWSER
        if settings.BROWSER_PATH:
            self.browser = self.playwright.chromium.launch(executable_path=settings.BROWSER_PATH, headless=headless)
        else:
            try:
                self.browser = self.playwright.chromium.launch(headless=headless)
            except Exception:  # Playwright's browser not installed: use Microsoft Edge (on every Windows)
                self.browser = self.playwright.chromium.launch(channel="msedge", headless=headless)
        self.page = self.browser.new_page(ignore_https_errors=True)
        # "Are you sure?" pop-ups: yes for changes, no for read-only tasks
        self.page.on("dialog", lambda d: d.dismiss() if self.read_only else d.accept())
        self.page.goto(self.url, timeout=20000)
        self._settle()
        self._login_if_needed()

    def disconnect(self):
        if getattr(self, "browser", None):
            self.browser.close()
        if getattr(self, "playwright", None):
            self.playwright.stop()

    def get_config(self):
        return "(web page router: no config backup)"

    def send_config(self, commands):
        return self._agent("\n".join(commands), read_only=False)

    def run_commands(self, commands):
        return self._agent("\n".join(commands), read_only=True)

    # ---- the agent loop ----
    def _agent(self, task: str, read_only: bool) -> str:
        self.read_only = read_only
        system = SYSTEM_PROMPT + (READ_ONLY_RULES if read_only else "")
        history = []  # what we did, shown to the AI every turn
        tried = []    # (action, element, value), to notice when the AI is stuck
        started = time.monotonic()
        self._log(f"task: {task}")
        for step in range(1, MAX_STEPS + 1):
            if time.monotonic() - started > TIME_LIMIT:
                raise RuntimeError(f"Stopped after {TIME_LIMIT // 60} minutes. Steps:\n" + "\n".join(history))
            self._login_if_needed()  # the router may have logged us out
            elements = self._list_elements()[:MAX_ELEMENTS]
            user = (f"TASK:\n{task}\n\nDONE SO FAR:\n" + ("\n".join(history) or "(nothing yet)") +
                    f"\n\nPAGE {self.page.url}:\n{self._page_text()}\n\nELEMENTS:\n" + "\n".join(elements))
            self._log(f"step {step}: asking the AI ({len(elements)} elements on the page)...")
            answer = self.llm.ask_json(system, user, ACTION_SCHEMA)
            action, number, value = answer["action"], answer.get("element", -1), answer.get("value", "")
            self._log(f"step {step}: AI says {action} [{number}] {value!r} - {answer.get('reason', '')}")

            if action == "done":
                return "\n".join(history + [f"DONE: {answer.get('answer', '')}"])
            if action == "fail":
                raise RuntimeError("The AI could not do it on the web page: " + answer.get("answer", "")
                                   + "\nSteps:\n" + "\n".join(history))

            note = f"{step}. {action} [{number}]" + (f' "{value}"' if value else "")
            tried.append((action, number, value))
            try:
                element = self._find(number)
                if read_only and not self._allowed_read_only(action, value, element):
                    raise RuntimeError("not allowed in a read-only task")
                if action == "click":
                    element.click(timeout=5000)
                elif action == "fill":
                    element.fill(self._secret(value), timeout=5000)
                elif action == "select":
                    try:
                        element.select_option(label=value, timeout=5000)
                    except Exception:
                        element.select_option(value, timeout=5000)
                history.append(f"{note} - {answer.get('reason', '')}")
            except Exception as error:
                history.append(f"{note} - FAILED: {str(error).splitlines()[0]}")
            self._settle()

            if len(tried) >= 3 and tried[-1] == tried[-2] == tried[-3]:
                raise RuntimeError("The AI is repeating the same action. Steps:\n" + "\n".join(history))
        raise RuntimeError(f"Gave up after {MAX_STEPS} steps. Steps:\n" + "\n".join(history))

    # ---- helpers ----
    def _list_elements(self) -> list[str]:
        # Routers often use frames (a page inside the page), so we look in every frame.
        elements = []
        for frame in self.page.frames:
            try:
                elements += frame.evaluate(LIST_ELEMENTS_JS, len(elements))
            except Exception:
                pass  # frame still loading or gone
        return elements

    def _find(self, number: int):
        for frame in self.page.frames:
            locator = frame.locator(f'[data-ibn="{number}"]')
            if locator.count():
                return locator.first
        raise RuntimeError(f"element {number} is not on the page")

    def _page_text(self) -> str:
        texts = []
        for frame in self.page.frames:
            try:
                texts.append(frame.evaluate("document.body ? document.body.innerText : ''")[:1000])
            except Exception:
                pass
        return re.sub(r"\n\s*\n+", "\n", "\n".join(texts)).strip()[:MAX_TEXT]

    def _allowed_read_only(self, action: str, value: str, element) -> bool:
        """Read-only tasks may log in (type only the login placeholders) and click
        anything except buttons that change something (Apply, Save, Reboot...)."""
        if action == "fill":
            return value in ("{username}", "{password}")
        if action == "click":
            text = element.inner_text() or element.get_attribute("value") or ""
            return not CHANGING_WORDS.search(text)
        return False

    def _credentials(self) -> tuple[str, str]:
        return (self.device.get("username") or settings.DEVICE_USERNAME,
                self.device.get("password") or settings.DEVICE_PASSWORD)

    def _secret(self, value: str) -> str:
        username, password = self._credentials()
        return value.replace("{username}", username).replace("{password}", password)

    # ---- login without the AI ----
    LOGIN_WORDS = re.compile(r"log\s?in|sign\s?in", re.I)

    def _login_form(self):
        """(frame, login button) if the page is a login page, else None.
        A login page = a password box + very few other boxes + a "Login"/"Sign in" button.
        (A Wi-Fi settings page also has a password box, but no Login button.
        That check matters: we must never type the router password into a Wi-Fi password box.)"""
        for frame in self.page.frames:
            try:
                if not frame.locator("input[type=password]:visible").count():
                    continue
                boxes = frame.locator("input:visible:not([type=hidden]):not([type=button])"
                                      ":not([type=submit]):not([type=checkbox]):not([type=radio])").count()
                if boxes > 3:
                    continue
                for button in frame.locator("button:visible, input[type=submit]:visible, input[type=button]:visible, "
                                            "a:visible, [id*=login i]:visible").all()[:40]:
                    label = button.inner_text() or button.get_attribute("value") or button.get_attribute("id") or ""
                    if self.LOGIN_WORDS.search(label):
                        return frame, button
            except Exception:
                pass  # frame still loading or gone
        return None

    LOGIN_WAIT = 15  # seconds to wait for a login to finish (routers can be slow)

    def _login_if_needed(self):
        for attempt in (1, 2):
            form = self._login_form()
            if not form:
                return  # not a login page (or the login worked)
            frame, button = form
            self._log(f"login page found: logging in, try {attempt} (no AI needed)")
            username, password = self._credentials()
            user_box = frame.locator("input[type=text]:visible, input[type=email]:visible, input:not([type]):visible")
            if user_box.count():
                user_box.first.fill(username)
            password_box = frame.locator("input[type=password]:visible").first
            password_box.fill(password)
            if attempt == 1:
                button.click(timeout=5000)
            else:
                password_box.press("Enter")  # second try: some pages log in with Enter
            # wait (up to LOGIN_WAIT seconds) until the login page is gone
            for _ in range(self.LOGIN_WAIT):
                self.page.wait_for_timeout(1000)
                if not self._login_form():
                    self._log("logged in")
                    self._settle()
                    return
        # Still on the login page: say what the router's page shows, and keep a screenshot.
        try:
            message = frame.evaluate("document.body.innerText").strip().replace("\n", " ")[:300]
        except Exception:
            message = "?"
        try:
            os.makedirs("data", exist_ok=True)
            self.page.screenshot(path="data/login_failed.png")
        except Exception:
            pass
        raise RuntimeError(
            f"Login failed. The router's page says: \"{message}\"\n"
            "Check: 1) the username/password saved for this device, "
            "2) log out of the router in your own browser (many routers allow only ONE login at a time), "
            "3) some routers lock the login for a minute after wrong tries.\n"
            "Screenshot saved in data/login_failed.png")

    def _log(self, message: str):
        # shows up in the black start.bat window, so you can follow what happens
        print(f"[{self.device['name']}] {message}", flush=True)

    def _settle(self):
        """Wait until the page has finished loading after an action."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)
