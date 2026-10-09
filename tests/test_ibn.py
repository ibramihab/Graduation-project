"""Tests for the whole pipeline, with no real devices and no real AI.
Run them with:  pytest
"""
import os

import pytest

from ibn import pipeline
from ibn.infrastructure.drivers.simulated import FAKE_CONFIGS
from ibn.interface.web import create_app
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


def change(device, commands, rollback):
    return {"device": device, "commands": commands, "rollback": rollback}


def test_knowledge_base_graph(kb):
    assert {d["name"] for d in kb.list_devices()} == {"R1", "SW1"}
    assert kb.list_links() == [{"a": "R1", "b": "SW1"}]
    kb.add_link("SW1", "R1")  # same link the other way: no duplicate
    assert len(kb.list_links()) == 1
    assert kb.find_by_ip("10.0.0.2")["name"] == "SW1"


def test_validation_blocks_dangerous_commands(kb):
    plan = {"changes": [change("R1", ["reload"], ["x"])]}
    assert not validate(plan, kb)["ok"]


def test_validation_blocks_unknown_device(kb):
    plan = {"changes": [change("R9", ["vlan 10"], ["no vlan 10"])]}
    assert "not in the knowledge base" in validate(plan, kb)["errors"][0]


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
