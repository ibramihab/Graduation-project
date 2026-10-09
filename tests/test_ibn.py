"""Tests for the whole pipeline, with no real devices and no real AI.
Run them with:  pytest
"""
import os

import pytest

from ibn import pipeline
from ibn.infrastructure.drivers.simulated import FAKE_CONFIGS
from ibn.interface.web import create_app
from ibn.knowledge import graph_analysis
from ibn.knowledge.file_graph import FileGraph
from ibn.validation import validate


class FakeLLM:
    """Pretends to be the AI: always returns the plan we give it."""

    def __init__(self, plan):
        self.plan = plan

    def ask_json(self, system, user, schema):
        return self.plan


def make_neo4j():
    """Only runs with  TEST_NEO4J=1 pytest  because it DELETES the devices in Neo4j.
    Never use it on a Neo4j that holds your real network data."""
    from ibn import settings
    from ibn.knowledge.neo4j_graph import Neo4jGraph
    if os.getenv("TEST_NEO4J") != "1":
        pytest.skip("set TEST_NEO4J=1 to also test Neo4j")
    try:
        kb = Neo4jGraph(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    except Exception:
        pytest.skip("Neo4j is not running")
    kb._run("MATCH (n) WHERE n:Device OR n:Change DETACH DELETE n")  # start empty
    return kb


# Every test runs twice: once with the JSON file graph, once with Neo4j.
@pytest.fixture(params=["file", "neo4j"])
def kb(request, tmp_path):
    FAKE_CONFIGS.clear()
    kb = FileGraph(str(tmp_path / "kb.json")) if request.param == "file" else make_neo4j()
    kb.add_device({"name": "R1", "ip": "10.0.0.1", "vendor": "simulated", "state": "up"})
    kb.add_device({"name": "SW1", "ip": "10.0.0.2", "vendor": "simulated", "state": "up"})
    kb.add_link("R1", "SW1")
    return kb


def change(device, commands, rollback, type="config"):
    return {"device": device, "type": type, "commands": commands, "rollback": rollback}


def test_knowledge_base_graph(kb):
    assert {d["name"] for d in kb.list_devices()} == {"R1", "SW1"}
    assert kb.list_links() == [{"a": "R1", "b": "SW1"}]
    kb.add_link("SW1", "R1")  # same link the other way: no duplicate
    assert len(kb.list_links()) == 1
    kb.delete_link("SW1", "R1")  # either direction works
    assert kb.list_links() == []
    kb.add_link("R1", "SW1")
    assert kb.find_by_ip("10.0.0.2")["name"] == "SW1"


def test_validation_blocks_dangerous_commands(kb):
    plan = {"changes": [change("R1", ["reload"], ["x"])]}
    assert not validate(plan, kb)["ok"]


def test_validation_blocks_unknown_device(kb):
    plan = {"changes": [change("R9", ["vlan 10"], ["no vlan 10"])]}
    assert "not in the knowledge base" in validate(plan, kb)["errors"][0]


def test_check_steps_are_read_only(kb):
    ok = {"changes": [change("R1", ["ping 10.2.3.3", "show ip route"], [], type="check")]}
    assert validate(ok, kb)["ok"]
    for bad in (["vlan 10"], ["show run | redirect flash:x"]):
        plan = {"changes": [change("R1", bad, [], type="check")]}
        assert not validate(plan, kb)["ok"]


def test_ping_in_config_mode_is_refused(kb):
    plan = {"changes": [change("R1", ["ping 10.2.3.3"], ["x"])]}
    assert "can't run in config mode" in validate(plan, kb)["errors"][0]


def test_check_runs_without_changing_the_device(kb):
    llm = FakeLLM({"summary": "ping", "changes": [change("R1", ["ping 10.2.3.3"], [], type="check")]})
    plan = pipeline.propose("ping R3 from R1", kb, llm)
    result = pipeline.approve(plan["id"], kb)
    assert result["success"]
    assert result["results"][0]["status"] == "checked"
    assert "ping 10.2.3.3" in result["results"][0]["output"]
    assert "ping 10.2.3.3" not in FAKE_CONFIGS.get("R1", [])  # nothing was configured


def test_failed_check_is_reported_as_failed(kb, monkeypatch):
    from ibn.infrastructure.drivers.simulated import SimulatedDriver
    def broken(self, commands):
        raise TimeoutError("Read timed out")
    monkeypatch.setattr(SimulatedDriver, "run_commands", broken)
    llm = FakeLLM({"summary": "ping", "changes": [change("R1", ["ping 10.2.3.3"], [], type="check")]})
    plan = pipeline.propose("ping R3 from R1", kb, llm)
    result = pipeline.approve(plan["id"], kb)
    assert not result["success"]
    assert result["results"][0]["status"] == "check failed"


def test_unknown_interface_is_refused(kb):
    kb.update_device("R1", interfaces=["Ethernet0/0 10.1.2.1", "Ethernet0/1 unassigned"])
    good = {"changes": [change("R1", ["interface e0/1", "description test"], ["interface e0/1", "no description"])]}
    bad = {"changes": [change("R1", ["interface GigabitEthernet0/0", "description test"], ["x"])]}
    assert validate(good, kb)["ok"]
    assert "does not exist" in validate(bad, kb)["errors"][0]


class LearningLLM:
    """First answer is wrong, second (after seeing the errors) is right."""

    def __init__(self):
        self.requests = []

    def ask_json(self, system, user, schema):
        self.requests.append(user)
        command = "interface GigabitEthernet0/0" if len(self.requests) == 1 else "interface Ethernet0/0"
        return {"summary": "x", "changes": [change("R1", [command, "description x"], ["no description"])]}


def test_ai_fixes_its_plan_after_validation_errors(kb):
    kb.update_device("R1", interfaces=["Ethernet0/0 10.1.2.1"])
    llm = LearningLLM()
    plan = pipeline.propose("describe R1's first port", kb, llm)
    assert plan["validation"]["ok"] and plan["attempts"] == 2
    assert "does not exist" in llm.requests[1]  # the errors were sent back to the AI
    assert plan["intent"] == "describe R1's first port"


def test_happy_path(kb):
    llm = FakeLLM({"summary": "vlan", "changes": [change("SW1", ["conf t", "vlan 10", "name Sales"], ["no vlan 10"])]})
    plan = pipeline.propose("create vlan 10 on SW1", kb, llm)
    assert plan["validation"]["ok"]
    assert plan["changes"][0]["commands"] == ["vlan 10", "name Sales"]  # "conf t" removed

    result = pipeline.approve(plan["id"], kb)
    assert result["success"]
    assert "vlan 10" in FAKE_CONFIGS["SW1"]
    assert kb.get_history("SW1")[0]["success"] is True
    assert kb.get_device("SW1")["last_config"] == "hostname SW1"  # backup taken first


def test_failure_rolls_back_every_device(kb):
    llm = FakeLLM({"summary": "x", "changes": [
        change("R1", ["ip route 0.0.0.0 0.0.0.0 10.0.0.254"], ["no ip route 0.0.0.0 0.0.0.0 10.0.0.254"]),
        change("SW1", ["this is invalid"], ["undo sw1"]),
    ]})
    plan = pipeline.propose("break it", kb, llm)
    result = pipeline.approve(plan["id"], kb)

    assert not result["success"]
    statuses = [(r["device"], r["status"]) for r in result["results"]]
    assert statuses == [("R1", "applied"), ("SW1", "failed"),
                        ("SW1", "rolled back"), ("R1", "rolled back")]
    assert FAKE_CONFIGS["R1"][-1] == "no ip route 0.0.0.0 0.0.0.0 10.0.0.254"


def test_plan_can_only_be_approved_once(kb):
    llm = FakeLLM({"summary": "", "changes": [change("R1", ["hostname R1"], ["hostname R1"])]})
    plan = pipeline.propose("x", kb, llm)
    assert pipeline.approve(plan["id"], kb)["success"]
    assert not pipeline.approve(plan["id"], kb)["success"]


def test_web_api(kb):
    llm = FakeLLM({"summary": "vlan", "changes": [change("SW1", ["vlan 20"], ["no vlan 20"])]})
    client = create_app(kb, llm).test_client()
    assert client.get("/").status_code == 200
    assert len(client.get("/api/topology").json["devices"]) == 2

    plan = client.post("/api/intent", json={"text": "vlan 20 on SW1"}).json
    assert client.post(f"/api/approve/{plan['id']}").json["success"]


def build_lab(kb):
    """Your EVE-NG lab: SW1 - R1 - R2 - R3 - SW3 (R1 and SW1 already exist)."""
    for name in ("R2", "R3", "SW3"):
        kb.add_device({"name": name, "ip": "10.0.0.9", "vendor": "simulated", "state": "up"})
    for a, b in (("R1", "R2"), ("R2", "R3"), ("R3", "SW3")):
        kb.add_link(a, b)


def test_graph_questions(kb):
    build_lab(kb)
    assert graph_analysis.path(kb, "SW1", "SW3") == ["SW1", "R1", "R2", "R3", "SW3"]
    assert graph_analysis.independent_paths(kb, "SW1", "SW3") == 1
    assert graph_analysis.impact(kb, "R2") == [["R1", "SW1"], ["R3", "SW3"]]
    assert graph_analysis.impact(kb, "SW3") == []  # an edge device cuts nobody off
    assert graph_analysis.critical_devices(kb) == ["R1", "R2", "R3"]
    assert graph_analysis.path(kb, "SW1", "NOPE") == []

    kb.add_link("R1", "R3")  # like the tunnel: now there is a backup path around R2
    assert graph_analysis.independent_paths(kb, "R1", "R3") == 2
    assert graph_analysis.impact(kb, "R2") == []
    assert "R2" not in graph_analysis.critical_devices(kb)


def test_risky_change_on_critical_device_warns_what_would_break(kb):
    build_lab(kb)
    plan = {"changes": [change("R2", ["interface e0/1", "shutdown"], ["interface e0/1", "no shutdown"])]}
    warnings = " ".join(validate(plan, kb)["warnings"])
    assert "single point of failure" in warnings and "R3, SW3" in warnings


def test_graph_api(kb):
    build_lab(kb)
    client = create_app(kb, FakeLLM({})).test_client()
    assert client.get("/api/graph/path?a=SW1&b=SW3").json["path"][2] == "R2"
    assert client.get("/api/graph/impact/R2").json["groups"] == [["R1", "SW1"], ["R3", "SW3"]]
    assert client.get("/api/graph/critical").json["critical"] == ["R1", "R2", "R3"]
