"""Interface layer: a small web server (Flask) + one HTML page.

Every button on the page calls one of these URLs (a simple JSON API).
"""
import re

from flask import Flask, jsonify, render_template, request

from .. import pipeline
from ..infrastructure import discovery
from ..intent import get_llm
from ..knowledge import get_knowledge_base, graph_analysis
from ..vendors import VENDORS


# Short port names people type -> the full names the devices (and the validation) use.
SHORT_NAMES = {"e": "Ethernet", "eth": "Ethernet", "fa": "FastEthernet", "g": "GigabitEthernet",
               "gi": "GigabitEthernet", "te": "TenGigabitEthernet", "s": "Serial", "se": "Serial",
               "lo": "Loopback", "tu": "Tunnel", "vl": "Vlan", "po": "Port-channel"}


def interface_list(text) -> list[str]:
    """ "e0/0 192.168.1.1/24\nEthernet0/1 10.0.12.1" -> ["Ethernet0/0 192.168.1.1/24", "Ethernet0/1 10.0.12.1"]
    (the same format "Find links" saves: port name, then its IP)."""
    lines = text.splitlines() if isinstance(text, str) else list(text or [])
    result = []
    for line in lines:
        parts = line.replace(",", " ").split()
        if not parts:
            continue
        match = re.match(r"([A-Za-z-]+)\s*([\d/.:]+)$", parts[0])
        if match and match[1].lower() in SHORT_NAMES:
            parts[0] = SHORT_NAMES[match[1].lower()] + match[2]
        result.append(" ".join(parts))
    return result


def create_app(kb=None, llm=None) -> Flask:
    app = Flask(__name__)
    kb = kb or get_knowledge_base()
    llm = llm or get_llm()

    @app.get("/")
    def home():
        return render_template("index.html", vendors=VENDORS.values())  # vendor dropdown

    # ---- the main flow: type -> see plan -> approve ----
    @app.post("/api/intent")
    def intent():
        return jsonify(pipeline.propose(request.json["text"], kb, llm))

    @app.post("/api/approve/<plan_id>")
    def approve(plan_id):
        return jsonify(pipeline.approve(plan_id, kb))

    # ---- knowledge base: devices, links, history ----
    @app.get("/api/topology")
    def topology():
        # a device's own username and password are never sent to the page;
        # it only learns whether they are saved
        hidden = ("username", "password", "last_config")
        devices = [{**{k: v for k, v in d.items() if k not in hidden},
                    "has_username": bool(d.get("username")), "has_password": bool(d.get("password"))}
                   for d in kb.list_devices()]
        names = {d["name"] for d in devices}
        links = [l for l in kb.list_links() if l["a"] in names and l["b"] in names]  # skip broken links
        return jsonify({"devices": devices, "links": links})

    @app.post("/api/devices")
    def add_device():
        device = {k: v for k, v in request.json.items() if v not in ("", None)}
        if not device.get("name") or not device.get("ip"):
            return jsonify({"ok": False, "error": "Name and IP are required."})
        # The login boxes, when editing:
        #   username empty                -> use the username from .env
        #   password typed                -> save this new password
        #   password empty                -> keep the saved password (the page never shows it)...
        #   ...unless username is empty too -> forget both: use the full .env login
        # Interfaces typed by hand (one per line), for devices "Find links" can't read (e.g. simulated).
        # Box empty = no interfaces typed (the Edit button fills the box with the saved ones).
        if "interfaces" in request.json:
            device["interfaces"] = interface_list(request.json["interfaces"]) or None
        username_empty = "username" in request.json and not request.json["username"]
        password_empty = not request.json.get("password")
        if username_empty:
            device["username"] = None
            if password_empty:
                device["password"] = None
        kb.add_device(device)
        return jsonify({"ok": True})

    @app.delete("/api/devices/<name>")
    def delete_device(name):
        kb.delete_device(name)
        return jsonify({"ok": True})

    @app.post("/api/links")
    def add_link():
        # Match the typed names to real devices, ignoring CAPITALS and extra spaces ("r1 " -> "R1").
        by_name = {d["name"].strip().lower(): d["name"] for d in kb.list_devices()}
        a = by_name.get(str(request.json.get("a", "")).strip().lower())
        b = by_name.get(str(request.json.get("b", "")).strip().lower())
        if not a or not b:
            missing = [x for x, found in ((request.json.get("a"), a), (request.json.get("b"), b)) if not found]
            return jsonify({"ok": False, "error": f"No device named {', '.join(map(repr, missing))}."})
        if a == b:
            return jsonify({"ok": False, "error": "Choose two different devices."})
        kb.add_link(a, b, manual=True)
        return jsonify({"ok": True, "a": a, "b": b})

    @app.delete("/api/links")
    def delete_link():
        kb.delete_link(request.json["a"], request.json["b"])
        return jsonify({"ok": True})

    @app.get("/api/devices/<name>/history")
    def history(name):
        return jsonify(kb.get_history(name))

    # ---- graph questions (NetworkX) ----
    @app.get("/api/graph/path")
    def graph_path():
        a, b = request.args["a"], request.args["b"]
        return jsonify({"path": graph_analysis.path(kb, a, b),
                        "independent_paths": graph_analysis.independent_paths(kb, a, b)})

    @app.get("/api/graph/impact/<name>")
    def graph_impact(name):
        return jsonify({"groups": graph_analysis.impact(kb, name)})

    @app.get("/api/graph/critical")
    def graph_critical():
        return jsonify({"critical": graph_analysis.critical_devices(kb)})

    # ---- discovery ----
    @app.post("/api/discover")
    def discover():
        found = discovery.discover(kb, request.json["subnet"])
        return jsonify({"found": len(found)})

    @app.post("/api/reset")
    def reset():
        """Start a new topology: delete every device, link and history entry."""
        kb.clear()
        return jsonify({"ok": True})

    @app.post("/api/discover-links")
    def discover_links():
        errors = discovery.discover_links(kb)
        return jsonify({"errors": errors, "links": len(kb.list_links())})

    @app.post("/api/refresh")
    def refresh():
        discovery.refresh_states(kb)
        return jsonify({"ok": True})

    @app.errorhandler(Exception)
    def on_error(error):  # show errors on the page instead of a crash
        return jsonify({"error": str(error)}), 500

    return app
