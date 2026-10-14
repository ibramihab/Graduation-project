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
    assert kb.list_links() == [{"a": "R1", "b": "SW1", "manual": False}]
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


# ---- vendor profiles (ibn/vendors/) ----
from ibn.infrastructure.drivers import DRIVERS  # noqa: E402
from ibn.infrastructure.drivers.cli import CliDriver  # noqa: E402
from ibn.intent.translator import _clean  # noqa: E402
from ibn.vendors import VENDORS, get_vendor  # noqa: E402


def examples(profile):
    """The example plans written in a vendor's AI hints."""
    import json
    blocks = profile.ai_hints.split("Examples:")[-1].split("\n\n")
    return [json.loads(b[b.index("{"):]) for b in blocks if "{" in b]


def test_every_vendor_has_a_driver_and_valid_examples(tmp_path):
    for profile in VENDORS.values():
        assert profile.name in DRIVERS
        kb = FileGraph(str(tmp_path / f"{profile.name}.json"))
        for plan in examples(profile):
            for c in plan["changes"]:
                kb.add_device({"name": c["device"], "ip": "10.0.0.1",
                               "vendor": profile.name, "state": "up"})
            result = validate(plan, kb)
            assert result["ok"], (profile.name, result["errors"])


def test_vendor_rules_are_per_vendor(tmp_path):
    kb = FileGraph(str(tmp_path / "kb.json"))
    kb.add_device({"name": "HW1", "ip": "10.0.0.1", "vendor": "huawei", "state": "up"})
    kb.add_device({"name": "FW1", "ip": "10.0.0.2", "vendor": "fortigate", "state": "up"})
    # dangerous commands of each vendor
    assert not validate({"changes": [change("HW1", ["reset saved-configuration"], ["x"])]}, kb)["ok"]
    assert not validate({"changes": [change("FW1", ["execute factoryreset"], ["x"])]}, kb)["ok"]
    # each vendor's own read-only commands
    assert validate({"changes": [change("HW1", ["display vlan"], [], "check")]}, kb)["ok"]
    assert validate({"changes": [change("FW1", ["get system status"], [], "check")]}, kb)["ok"]
    assert not validate({"changes": [change("FW1", ["show"], [], "config")]}, kb)["ok"]
    assert not validate({"changes": [change("HW1", ["show vlan"], [], "check")]}, kb)["ok"]


def test_huawei_short_interface_names(tmp_path):
    kb = FileGraph(str(tmp_path / "kb.json"))
    kb.add_device({"name": "HW1", "ip": "10.0.0.1", "vendor": "huawei", "state": "up",
                   "interfaces": ["GigabitEthernet0/0/1 10.0.5.1"]})
    ok = change("HW1", ["interface GE0/0/1", "undo shutdown", "quit"], ["x"])
    bad = change("HW1", ["interface GE0/0/9", "undo shutdown", "quit"], ["x"])
    assert validate({"changes": [ok]}, kb)["ok"]
    assert not validate({"changes": [bad]}, kb)["ok"]


def test_vendor_interface_parsing():
    huawei = """Interface                         IP Address/Mask      Physical   Protocol
GigabitEthernet0/0/1              10.0.5.1/24          up         up
LoopBack0                         unassigned           up         up(s)"""
    assert get_vendor("huawei").parse_interfaces(huawei) == [
        "GigabitEthernet0/0/1 10.0.5.1", "LoopBack0 unassigned"]
    forti = """config system interface
    edit "port1"
        set ip 192.168.1.99 255.255.255.0
        config ipv6
        end
    next
    edit "port2"
    next
end"""
    assert get_vendor("fortigate").parse_interfaces(forti) == ["port1 192.168.1.99", "port2 unassigned"]


def test_wrapper_lines_are_cleaned_per_vendor():
    assert _clean(["conf t", "vlan 10", "end"], get_vendor("cisco_ios").wrapper_lines) == ["vlan 10"]
    forti = ["config system interface", "edit port2", "set ip 1.1.1.1 255.0.0.0", "next", "end"]
    assert _clean(forti, get_vendor("fortigate").wrapper_lines) == forti  # "end" is needed!


def test_driver_uses_the_vendor_error_markers():
    class FakeConn:
        def send_config_set(self, commands):
            return "Command fail. Return code -61"
    driver = CliDriver({"name": "FW1", "ip": "1.1.1.1", "vendor": "fortigate"})
    driver.profile, driver.conn = get_vendor("fortigate"), FakeConn()
    with pytest.raises(RuntimeError):
        driver.send_config(["config system interface"])


def test_vendor_dropdown_comes_from_profiles(tmp_path):
    client = create_app(FileGraph(str(tmp_path / "kb.json")), FakeLLM({})).test_client()
    page = client.get("/").text
    assert 'value="fortigate"' in page and 'value="huawei"' in page


# ---- starting over / keeping the knowledge base clean ----
def test_clear_starts_a_new_topology(kb):
    kb.record_change("R1", {"time": "t", "intent": "x", "commands": []})
    kb.clear()
    assert kb.list_devices() == [] and kb.list_links() == []
    kb.add_device({"name": "R1", "ip": "10.0.0.9", "vendor": "simulated"})
    assert kb.get_history("R1") == []  # the old R1's history is gone


def test_deleting_a_device_deletes_its_history(kb):
    kb.record_change("R1", {"time": "t", "intent": "x", "commands": []})
    kb.delete_device("R1")
    kb.add_device({"name": "R1", "ip": "10.0.0.9", "vendor": "simulated"})
    assert kb.get_history("R1") == []


def test_reset_url(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    assert client.post("/api/reset").json["ok"]
    assert client.get("/api/topology").json["devices"] == []


def test_find_links_removes_links_that_are_gone(kb, monkeypatch):
    from ibn.infrastructure import discovery
    for name in ("R1", "R2", "R3", "SW1"):
        kb.add_device({"name": name, "ip": "10.0.0.1", "vendor": "cisco_ios", "state": "up"})
    kb.add_link("R1", "R2")                 # old cable, no longer there
    kb.add_link("R1", "R3", manual=True)    # added by hand (e.g. a tunnel)
    neighbors = {"R1": ["SW1"], "SW1": ["R1"], "R2": [], "R3": []}

    class FakeDriver:
        def __init__(self, device): self.name = device["name"]
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get_interfaces(self): return []
        def get_neighbors(self): return neighbors[self.name]
    monkeypatch.setattr(discovery, "get_driver", FakeDriver)

    assert discovery.discover_links(kb) == []
    links = {frozenset((l["a"], l["b"])) for l in kb.list_links()}
    assert frozenset(("R1", "SW1")) in links      # found now
    assert frozenset(("R1", "R2")) not in links   # gone: removed
    assert frozenset(("R1", "R3")) in links       # manual: kept


def test_find_links_keeps_links_of_devices_it_could_not_reach(kb, monkeypatch):
    from ibn.infrastructure import discovery
    for name in ("R1", "R2"):
        kb.add_device({"name": name, "ip": "10.0.0.1", "vendor": "cisco_ios", "state": "up"})
    kb.add_link("R1", "R2")

    def broken(device):
        raise RuntimeError("Authentication failed")
    monkeypatch.setattr(discovery, "get_driver", broken)
    errors = discovery.discover_links(kb)
    assert any(e.startswith("R1:") for e in errors) and any(e.startswith("R2:") for e in errors)
    assert {frozenset((l["a"], l["b"])) for l in kb.list_links()} >= {frozenset(("R1", "R2"))}


def test_clearing_the_username_goes_back_to_env_login(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "vendor": "cisco_ios",
                                      "username": "wrong", "password": "secret"})
    assert kb.get_device("R2")["username"] == "wrong"
    # edit: username box emptied, password box empty
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "vendor": "cisco_ios",
                                      "username": "", "password": ""})
    device = kb.get_device("R2")
    assert not device.get("username") and not device.get("password")


def test_change_only_the_password(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    # device with its own username
    client.post("/api/devices", json={"name": "R1", "ip": "10.0.0.1", "username": "admin", "password": "old"})
    client.post("/api/devices", json={"name": "R1", "ip": "10.0.0.1", "username": "admin", "password": "new"})
    assert kb.get_device("R1")["username"] == "admin" and kb.get_device("R1")["password"] == "new"
    # device that uses the .env username: only a password is typed
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "username": "", "password": "p2"})
    assert not kb.get_device("R2").get("username") and kb.get_device("R2")["password"] == "p2"
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "username": "", "password": "p3"})
    assert kb.get_device("R2")["password"] == "p3"
    # the page learns only WHETHER a password is saved, never the password
    page_devices = client.get("/api/topology").json["devices"]
    r2 = next(d for d in page_devices if d["name"] == "R2")
    assert r2["has_password"] is True and "password" not in r2


def test_empty_password_keeps_the_saved_one(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "username": "admin", "password": "p1"})
    client.post("/api/devices", json={"name": "R2", "ip": "10.0.0.2", "username": "admin", "password": ""})
    assert kb.get_device("R2")["password"] == "p1"


def test_device_needs_name_and_ip(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    assert client.post("/api/devices", json={"name": "R9", "ip": ""}).json["ok"] is False


def test_manual_link_names_ignore_capitals_and_spaces(kb):
    client = create_app(kb, FakeLLM({})).test_client()
    r = client.post("/api/links", json={"a": " r1", "b": "sw1 "}).json
    assert r["ok"] and (r["a"], r["b"]) == ("R1", "SW1")
    assert client.post("/api/links", json={"a": "R1", "b": "R9"}).json["ok"] is False
    assert client.post("/api/links", json={"a": "R1", "b": "r1"}).json["ok"] is False
    links = client.get("/api/topology").json["links"]
    assert all(l["a"] in ("R1", "SW1") and l["b"] in ("R1", "SW1") for l in links)


def test_ping_counts_a_real_reply_even_if_the_first_packet_is_lost(monkeypatch):
    from ibn.infrastructure import discovery

    class Result:
        def __init__(self, code, out): self.returncode, self.stdout = code, out.encode()
    replies = {
        "lost-then-ok": Result(0, "Request timed out.\nReply from 10.0.0.1: bytes=32 time=2ms TTL=255"),
        "unreachable": Result(0, "Reply from 10.0.0.9: Destination host unreachable."),
        "other-language": Result(0, "\u0627\u0644\u0631\u062f 10.0.0.5"),  # no "TTL" text, but SSH answers
        "nothing": Result(1, "Request timed out.\nRequest timed out."),
    }
    monkeypatch.setattr(discovery.subprocess, "run", lambda command, **kw: replies[command[-1]])
    monkeypatch.setattr(discovery, "open_ports", lambda ip, ports=None: ["ssh"] if ip == "other-language" else [])
    assert discovery.ping("lost-then-ok") is True
    assert discovery.ping("unreachable") is False
    assert discovery.ping("other-language") is True
    assert discovery.ping("nothing") is False
