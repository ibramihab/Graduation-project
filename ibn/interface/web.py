"""Interface layer: a small web server (Flask) + one HTML page.

Every button on the page calls one of these URLs (a simple JSON API).
"""
from flask import Flask, jsonify, render_template, request

from .. import pipeline
from ..infrastructure import discovery
from ..intent import get_llm
from ..knowledge import get_knowledge_base, graph_analysis


def create_app(kb=None, llm=None) -> Flask:
    app = Flask(__name__)
    kb = kb or get_knowledge_base()
    llm = llm or get_llm()

    @app.get("/")
    def home():
        return render_template("index.html")

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
        devices = [{k: v for k, v in d.items() if k not in ("password", "last_config")}
                   for d in kb.list_devices()]
        return jsonify({"devices": devices, "links": kb.list_links()})

    @app.post("/api/devices")
    def add_device():
        device = {k: v for k, v in request.json.items() if v not in ("", None)}
        kb.add_device(device)
        return jsonify({"ok": True})

    @app.delete("/api/devices/<name>")
    def delete_device(name):
        kb.delete_device(name)
        return jsonify({"ok": True})

    @app.post("/api/links")
    def add_link():
        kb.add_link(request.json["a"], request.json["b"])
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

    @app.post("/api/discover-links")
    def discover_links():
        return jsonify({"errors": discovery.discover_links(kb)})

    @app.post("/api/refresh")
    def refresh():
        discovery.refresh_states(kb)
        return jsonify({"ok": True})

    @app.errorhandler(Exception)
    def on_error(error):  # show errors on the page instead of a crash
        return jsonify({"error": str(error)}), 500

    return app
