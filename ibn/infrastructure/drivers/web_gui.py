"""Devices with only a web page (e.g. home routers). No CLI at all.

How it works (simple version):
  1. download the router's settings page (HTML)
  2. find the <form>s on the page
  3. ask the LLM: "which form and which fields do I fill to do this task?"
  4. submit that form, like a person clicking "Save"

The device needs a "url" (e.g. http://192.168.1.1/wireless.html).
"Commands" for this driver are plain English steps, e.g. "set wifi name to Home5G".
"""
import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ... import settings
from .base import Driver

FILL_SCHEMA = {
    "type": "object",
    "properties": {
        "form_index": {"type": "integer"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["form_index", "fields"],
    "additionalProperties": False,
}


class WebGuiDriver(Driver):
    def connect(self):
        self.url = self.device.get("url") or f"http://{self.device['ip']}/"
        self.session = requests.Session()
        self.session.auth = (self.device.get("username") or settings.DEVICE_USERNAME,
                             self.device.get("password") or settings.DEVICE_PASSWORD)

    def disconnect(self):
        self.session.close()

    def _read_forms(self) -> list[dict]:
        html = self.session.get(self.url, timeout=10).text
        forms = []
        for form in BeautifulSoup(html, "html.parser").find_all("form"):
            fields = {}
            for tag in form.find_all(["input", "select", "textarea"]):
                if tag.get("name"):
                    fields[tag["name"]] = tag.get("value", "")
            forms.append({"action": form.get("action", ""),
                          "method": form.get("method", "post").lower(),
                          "fields": fields})
        return forms

    def get_config(self):
        # The current values in the page's forms are our "config backup".
        return json.dumps(self._read_forms(), indent=2)

    def send_config(self, commands):
        from ...intent import get_llm  # the AI tool that reads the page
        forms = self._read_forms()
        answer = get_llm().ask_json(
            "You fill in router web forms. Pick the form and the field values that "
            "perform the task. Only use field names that exist in the form.",
            f"Forms on the page:\n{json.dumps(forms, indent=2)}\n\nTask:\n" + "\n".join(commands),
            FILL_SCHEMA,
        )
        form = forms[answer["form_index"]]
        data = dict(form["fields"])  # keep existing values...
        data.update({f["name"]: f["value"] for f in answer["fields"]})  # ...change only these
        target = urljoin(self.url, form["action"])
        if form["method"] == "get":
            response = self.session.get(target, params=data, timeout=10)
        else:
            response = self.session.post(target, data=data, timeout=10)
        response.raise_for_status()
        return f"Submitted {list(data)} to {target} (HTTP {response.status_code})"
