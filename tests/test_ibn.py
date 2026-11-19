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


def test_invalid_vlan_number_is_refused(kb):
    for bad in (["vlan 5000", "name Test"], ["vlan 0"], ["interface e0/1", "switchport access vlan 4095"],
                ["interface e0/1", "switchport trunk allowed vlan add 4095"],
                ["interface e0/1", "switchport trunk allowed vlan 10,20-5000"],
                ["vlan batch 10 to 5000"], ["interface e0/0.9", "encapsulation dot1Q 5000"]):
        plan = {"changes": [change("SW1", bad, ["no vlan 1"])]}
        result = validate(plan, kb)
        assert not result["ok"] and "invalid VLAN number" in result["errors"][0]
    for good in (["vlan 1"], ["vlan 10", "name Sales"], ["vlan 4094"],
                 ["interface e0/1", "switchport trunk allowed vlan add 10,20-30"],
                 ["spanning-tree vlan 10 priority 4096"]):
        assert validate({"changes": [change("SW1", good, ["no vlan 10"])]}, kb)["ok"]


def test_change_on_the_management_interface_warns(kb):
    # SW1 is reached on 10.0.0.2, which is on Vlan1
    kb.update_device("SW1", interfaces=["Vlan1 10.0.0.2/24", "Ethernet0/1"])

    def warnings(commands):
        # a correct rollback (puts the management IP back), so only the warnings are tested here
        rollback = ["interface Vlan1", "no shutdown", "ip address 10.0.0.2 255.255.255.0"]
        result = validate({"changes": [change("SW1", commands, rollback)]}, kb)
        assert result["ok"]  # a warning, not an error: the user may really want it
        return " ".join(result["warnings"])

    assert "cuts the program's connection" in warnings(["interface Vlan1", "shutdown"])
    assert "cuts the program's connection" in warnings(["interface vlan 1", "no ip address"])
    assert "changes the management IP" in warnings(["interface Vlan1", "ip address 10.0.0.50 255.255.255.0"])
    # Not the management interface, or nothing that cuts us off: no management warning
    assert "management" not in warnings(["interface Ethernet0/1", "shutdown"])
    assert "management" not in warnings(["interface Vlan1", "description mgmt"])
    assert "management" not in warnings(["interface Vlan1", "ip address 10.0.0.2 255.255.255.0"])
    assert "management" not in warnings(["interface Vlan1", "ip address 10.9.9.9 255.255.255.0 secondary"])
    # The IP was typed with spaces around it on the web page: still the same device IP
    kb.update_device("SW1", ip="   10.0.0.2 ")
    assert "cuts the program's connection" in warnings(["interface Vlan1", "shutdown"])


def test_rollback_must_not_cut_the_device_off(kb):
    kb.update_device("SW1", interfaces=["Vlan1 10.0.0.2/24", "Ethernet0/1"])
    move = ["interface Vlan1", "ip address 10.0.0.50 255.255.255.0"]

    def errors(commands, rollback):
        return " ".join(validate({"changes": [change("SW1", commands, rollback)]}, kb)["errors"])

    # The real mistake the AI made: "undo" the new IP by deleting the whole interface
    bad = errors(move, ["no interface Vlan1", "no ip address 10.0.0.50 255.255.255.0"])
    assert "deletes Vlan1" in bad
    assert "ip address 10.0.0.2 255.255.255.0" in bad  # it tells the AI the right rollback
    # A rollback that forgets the old IP
    assert "must put the management IP back" in errors(move, ["interface Vlan1", "no ip address"])
    # Deleting the management interface is wrong in any rollback
    assert "deletes Vlan1" in errors(["interface Vlan1", "description mgmt"], ["no interface vlan 1"])
    # The right rollback passes
    assert errors(move, ["interface Vlan1", "ip address 10.0.0.2 255.255.255.0"]) == ""


def test_invalid_ip_address_is_refused(kb):
    def errors(command):
        return " ".join(validate({"changes": [change("R1", ["interface Loopback5", command],
                                                     ["no interface Loopback5"])]}, kb)["errors"])

    assert "invalid IP address 300.1.1.1" in errors("ip address 300.1.1.1 255.255.255.255")
    assert "invalid IP address 10.1.1" in errors("ip address 10.1.1 255.255.255.0")
    assert "invalid mask 255.0.255.0" in errors("ip address 10.1.1.1 255.0.255.0")
    assert "did you mean 255.255.255.0" in errors("ip address 10.1.1.1 0.0.0.255")  # an ACL wildcard
    assert "invalid mask 33" in errors("ip address 10.1.1.1/33")
    assert "network address" in errors("ip address 10.1.1.0 255.255.255.0")
    assert "broadcast address" in errors("ip address 10.1.1.255 255.255.255.0")
    # Good ones (Cisco, Huawei "24", Arista "/24", FortiGate, /31, /32, secondary, removing an IP)
    for good in ("ip address 10.1.1.1 255.255.255.0", "ip address 10.1.1.1 24", "ip address 10.1.1.1/24",
                 "set ip 10.1.1.1 255.255.255.0", "ip address 10.1.1.0 255.255.255.254",
                 "ip address 5.5.5.5 255.255.255.255", "ip address 10.9.9.9 255.255.255.0 secondary",
                 "no ip address 300.1.1.1 255.255.255.0", "ip address dhcp"):
        assert errors(good) == "", good


def test_the_ai_may_not_change_the_users_values(kb):
    def errors(request, commands):
        plan = {"intent": request, "changes": [change("R1", commands, ["no interface Loopback5"])]}
        return " ".join(validate(plan, kb)["errors"])

    # The AI changed a valid IP the user asked for (10.1.1.5 -> 10.1.1.1)
    bad = errors("Set the IP of Ethernet0/0 on R1 to 10.1.1.5/24",
                 ["interface Ethernet0/0", "ip address 10.1.1.1 255.255.255.0"])
    assert "You asked for IP address 10.1.1.5" in bad and "it uses 10.1.1.1 instead" in bad
    # Kept as asked: no error (masks and IPs the network already has are not "values to keep")
    assert errors("Set the IP of Ethernet0/0 on R1 to 10.1.1.1/24",
                  ["interface Ethernet0/0", "ip address 10.1.1.1 255.255.255.0"]) == ""
    assert errors("Change R1's IP from 10.0.0.1 to 10.0.0.9 255.255.255.0",
                  ["interface Ethernet0/0", "ip address 10.0.0.9 255.255.255.0"]) == ""
    # On the second try, the errors we sent back are not the user's words
    assert errors("Set R1's loopback to 5.5.5.5/32\n\nYour previous plan was rejected by the safety "
                  "checks:\n- R1: 'ip address 300.1.1.1 ...'", ["interface Loopback5", "ip address 5.5.5.5 32"]) == ""


def test_wrong_ip_in_the_request_is_refused_in_our_words(kb):
    from ibn.validation.validator import request_problems
    assert "network address" in request_problems("Set the IP of interface Ethernet0/0 on R2 to 10.1.1.0/24")[0]
    assert "broadcast address" in request_problems("Set the IP of interface e0/2 on R2 to 172.16.0.255/24")[0]
    assert "invalid IP address 300.1.1.1" in request_problems("Create loopback 5 with IP 300.1.1.1/32 on R1")[0]
    assert "invalid IP address 10.5.5" in request_problems("Set the IP of interface e0/1 on R1 to 10.5.5/24")[0]
    assert "invalid mask" in request_problems("Set the IP of interface e0/1 on R1 to 10.5.5.1 with mask 255.0.255.0")[0]
    # Fine: a good IP, a /31 link, a network address in a route, a version number
    for ok in ("Set the IP of interface Ethernet0/0 on R2 to 10.1.1.1/24",
               "Set the IP of interface e0/1 on R1 to 10.0.12.0/31",
               "Add a static route to 192.168.5.0/24 via 10.1.2.2 on R1",
               "Upgrade R1 to IOS 15.2.4"):
        assert request_problems(ok) == [], ok

    # The whole flow: the AI "fixes" 10.1.1.0 into 10.1.1.1. We don't ask it again, we hide its plan,
    # and the message is ours, with no other IP suggested.
    llm = FakeLLM({"summary": "The correct IP is 10.1.1.1/24", "changes": [
        change("R1", ["interface Ethernet0/0", "ip address 10.1.1.1 255.255.255.0"], ["no ip address"])]})
    plan = pipeline.propose("Set the IP of interface Ethernet0/0 on R1 to 10.1.1.0/24", kb, llm)
    assert plan["attempts"] == 1 and plan["changes"] == [] and not plan["validation"]["ok"]
    assert plan["summary"].startswith("This can't be done.") and "10.1.1.1" not in plan["summary"]
    assert all(e.startswith("Your request:") for e in plan["validation"]["errors"])


class AnswersInTurn:
    """A fake AI that gives the next answer from a list each time it is asked."""
    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []

    def ask_json(self, system, user, schema):
        self.requests.append(user)
        return self.answers.pop(0)


def test_refused_valid_ip_gets_a_second_try_and_our_words(kb):
    request = "Give interface Ethernet0/1 on R1 the IP 10.0.12.0/31"  # a wording the program doesn't write itself
    refusal = {"summary": "Impossible, use 10.0.12.1/31 or 10.0.12.2/31", "changes": []}
    good = {"summary": "x", "changes": [change("R1", ["interface Ethernet0/1",
            "ip address 10.0.12.0 255.255.255.254"], ["interface Ethernet0/1", "no ip address"])]}

    # 1st answer: a refusal. We say the IP is valid and ask again; the 2nd answer is a good plan.
    llm = AnswersInTurn(refusal, good)
    plan = pipeline.propose(request, kb, llm)
    assert plan["validation"]["ok"] and plan["attempts"] == 2
    assert "10.0.12.0/31) were checked by the program and are valid" in llm.requests[1]

    # Refused twice: its wrong reasons and its IPs are hidden, the message is ours.
    plan = pipeline.propose(request, kb, AnswersInTurn(refusal, refusal))
    assert not plan["validation"]["ok"] and plan["summary"].startswith("The AI couldn't make a plan")
    assert "10.0.12.1" not in plan["summary"] and "10.0.12.1" not in " ".join(plan["validation"]["errors"])

    # A request without IPs: the AI's own answer is kept, and it's not asked again
    llm = AnswersInTurn({"summary": "Too vague: say what to change", "changes": []})
    plan = pipeline.propose("Make the network faster", kb, llm)
    assert plan["attempts"] == 1 and plan["summary"] == "Too vague: say what to change"


def test_the_door_to_the_lab_warns(kb, monkeypatch):
    # The lab file: this PC is 192.168.43.1, R1 is reached on its Loopback0 (10.0.0.1)
    # through Ethernet0/3 (192.168.43.2/24). Every device goes through that door.
    from ibn.validation import validator
    monkeypatch.setattr(validator, "local_ips", lambda: ["127.0.0.1", "192.168.43.1"])
    kb.update_device("R1", interfaces=["Loopback0 10.0.0.1/32", "Ethernet0/3 192.168.43.2/24",
                                       "Ethernet0/1 10.1.2.1/24"])

    def warnings(commands):
        result = validate({"changes": [change("R1", commands, ["interface Ethernet0/3", "no shutdown"])]}, kb)
        return " ".join(result["warnings"])

    assert "cut the program off from EVERY device" in warnings(["interface Ethernet0/3", "shutdown"])
    assert "this PC (192.168.43.1)" in warnings(["interface e0/3", "ip address 192.168.50.2 255.255.255.0"])
    assert "EVERY device" not in warnings(["interface Ethernet0/1", "shutdown"])   # an ordinary port
    assert "EVERY device" not in warnings(["interface Ethernet0/3", "description to PC"])


def test_ip_conflicts_are_refused(kb):
    # As "Find links & IPs" saves them from real devices (Cisco with masks)
    kb.update_device("R1", interfaces=["Loopback0 10.0.0.1/32", "Ethernet0/0 10.0.12.1/24",
                                       "Ethernet0/1 unassigned"])
    kb.update_device("SW1", interfaces=["Vlan1 10.0.1.11/24"])

    def errors(*changes):
        return " ".join(validate({"changes": list(changes)}, kb)["errors"])

    def set_ip(device, interface, ip_line, rollback=("no ip address",)):
        return change(device, [f"interface {interface}", ip_line], [f"interface {interface}", *rollback])

    # Same IP on another device, and another device's management IP (SW1 is reached on 10.0.0.2)
    assert "10.0.12.1 is already used on R1 Ethernet0/0" in errors(
        set_ip("SW1", "Vlan2", "ip address 10.0.12.1 255.255.255.0"))
    assert "10.0.0.2 is already used on SW1 (its management IP)" in errors(
        set_ip("R1", "e0/1", "ip address 10.0.0.2 255.255.255.0"))
    # Same IP on two interfaces of one device; overlapping subnets on one device (Cisco refuses it)
    assert "already used on R1 Ethernet0/0" in errors(set_ip("R1", "e0/1", "ip address 10.0.12.1 255.255.255.0"))
    assert "overlaps with Ethernet0/0 (10.0.12.1/24)" in errors(set_ip("R1", "e0/1", "ip address 10.0.12.200 255.255.255.0"))
    # Two devices given the same new IP in one plan
    assert "10.5.5.5 is already used on R1" in errors(set_ip("R1", "e0/1", "ip address 10.5.5.5 255.255.255.0"),
                                                     set_ip("SW1", "Vlan5", "ip address 10.5.5.5 255.255.255.0"))
    # Other vendors' syntax: Huawei "24", FortiGate "set ip"
    assert "already used" in errors(set_ip("SW1", "Vlanif5", "ip address 10.0.12.1 24"))
    assert "already used" in errors(change("SW1", ['edit "port1"', "set ip 10.0.12.1 255.255.255.0"], ["unset ip"]))

    # Fine: same interface again, a new free IP, a different subnet, a /31, and MOVING an IP in one plan
    for ok in ([set_ip("R1", "Ethernet0/0", "ip address 10.0.12.1 255.255.255.0")],
               [set_ip("R1", "e0/0", "ip address 10.0.12.9 255.255.255.0")],
               [set_ip("R1", "e0/1", "ip address 10.0.13.1 255.255.255.0")],
               [set_ip("R1", "e0/1", "ip address 10.0.99.0 255.255.255.254")],
               [change("R1", ["interface Ethernet0/0", "no ip address"], ["interface Ethernet0/0", "ip address 10.0.12.1 255.255.255.0"]),
                set_ip("SW1", "Vlan2", "ip address 10.0.12.1 255.255.255.0")]):
        assert errors(*ok) == "", ok


def test_renaming_an_existing_vlan_warns(kb, monkeypatch):
    def warnings(commands, device="SW1"):
        return " ".join(validate({"changes": [change(device, commands, ["no vlan 10"])]}, kb)["warnings"])

    # Made by the program before (a successful change in the history)
    kb.record_change("SW1", {"time": "2020-01-01T10:00:00", "type": "config", "success": True,
                             "commands": ["vlan 10", "name HR"]})
    assert "VLAN 10 already exists on SW1 as 'HR': this plan renames it to 'Sales'" in warnings(["vlan 10", "name Sales"])
    assert "already exists" not in warnings(["vlan 10", "name HR"])      # same name
    assert "already exists" not in warnings(["vlan 20", "name Sales"])   # a new VLAN
    assert "already exists" not in warnings(["vlan 10", "name Sales"], device="R1")  # another device
    # A failed (rolled back) change doesn't count; a later "no vlan 10" deletes it
    kb.record_change("SW1", {"time": "2020-01-01T10:05:00", "type": "config", "success": False,
                             "commands": ["vlan 10", "name Wrong"]})
    assert "as 'HR'" in warnings(["vlan 10", "name Sales"])
    kb.record_change("SW1", {"time": "2020-01-01T10:10:00", "type": "config", "success": True,
                             "commands": ["no vlan 10"]})
    assert "already exists" not in warnings(["vlan 10", "name Sales"])

    # A real switch: "Find links & IPs" reads its VLANs (and only later changes count on top)
    from ibn.infrastructure import discovery

    class Switch:
        def __init__(self, device): self.device = device
        def __enter__(self): return self
        def __exit__(self, *error): return False
        def get_interfaces(self): return []
        def get_neighbors(self): return []
        def get_vlans(self): return ["1 default", "30 Finance"] if self.device["name"] == "SW1" else []

    monkeypatch.setattr(discovery, "get_driver", lambda device: Switch(device))
    discovery.discover_links(kb)
    assert kb.get_device("SW1")["vlans"] == ["1 default", "30 Finance"]
    assert "vlans" not in kb.get_device("R1")  # a router has none
    assert "VLAN 30 already exists on SW1 as 'Finance'" in warnings(["vlan 30", "name Guests"])
    assert "already exists" not in warnings(["vlan 10", "name Sales"])  # gone from the switch


def test_missing_references_warn(kb):
    def warnings(*changes):
        return " ".join(validate({"changes": list(changes)}, kb)["warnings"])

    # 1-2. Access lists: used but never created -> Cisco filters nothing
    apply_101 = change("R1", ["interface Ethernet0/0", "ip access-group 101 in"],
                       ["interface Ethernet0/0", "no ip access-group 101 in"])
    assert "uses access list 101" in warnings(apply_101) and "filters NOTHING" in warnings(apply_101)
    assert "logins are accepted from anywhere" in warnings(
        change("R1", ["line vty 0 4", "access-class 10 in"], ["line vty 0 4", "no access-class 10 in"]))
    # ...not when the plan creates it, or the device's backup / the program's history has it
    assert "access list" not in warnings(change("R1", ["access-list 101 deny ip any host 10.9.9.9",
                                                      "access-list 101 permit ip any any",
                                                      "interface Ethernet0/0", "ip access-group 101 in"],
                                                ["no access-list 101"]))
    kb.save_backup("R1", "hostname R1\nip access-list extended BLOCK\n deny ip any any\naccess-list 101 permit ip any any")
    assert "access list" not in warnings(apply_101)
    assert "access list" not in warnings(change("R1", ["interface Ethernet0/0", "ip access-group BLOCK out"], ["x"]))

    # 3. A port in a VLAN that doesn't exist -> the switch creates it with no name
    port_60 = change("SW1", ["interface Ethernet0/1", "switchport access vlan 60"], ["interface Ethernet0/1", "no switchport access vlan"])
    assert "puts a port in VLAN 60" in warnings(port_60)
    assert "VLAN 60" not in warnings(change("SW1", ["vlan 60", "name Users"], ["no vlan 60"]), port_60)  # created in the plan
    assert "puts a port" not in warnings(change("SW1", ["interface Ethernet0/1", "switchport access vlan 1"], ["x"]))
    kb.update_device("SW1", vlans=["1 default", "60 Users"], vlans_read_at="2020-01-01T00:00:00")  # read from the switch
    assert "puts a port" not in warnings(port_60)

    # 4. A static route whose next hop isn't on a connected network
    route = lambda hop: change("R1", [f"ip route 192.168.5.0 255.255.255.0 {hop}"], [f"no ip route 192.168.5.0 255.255.255.0 {hop}"])
    assert "next hop" not in warnings(route("10.0.12.2"))  # no masks saved yet: can't tell, no warning
    kb.update_device("R1", interfaces=["Ethernet0/0 10.0.12.1/24", "Loopback0 10.0.0.1/32"])
    assert "next hop" not in warnings(route("10.0.12.2"))
    assert "the next hop 10.9.9.1" in warnings(route("10.9.9.1"))
    assert "next hop" not in warnings(change("R1", ["interface Ethernet0/1", "ip address 10.9.9.2 255.255.255.0"],
                                             ["interface Ethernet0/1", "no ip address"]), route("10.9.9.1"))


def test_changing_a_device_the_user_didnt_name_warns(kb):
    def warnings(request, *changes):
        return " ".join(validate({"intent": request, "changes": list(changes)}, kb)["warnings"])

    vlan_sw1 = change("SW1", ["vlan 20", "name IT"], ["no vlan 20"])
    subif_r1 = change("R1", ["interface Ethernet0/0.20", "encapsulation dot1Q 20"], ["no interface Ethernet0/0.20"])
    assert "R1: you didn't name R1 in your request" in warnings("Create VLAN 20 named IT on sw1", vlan_sw1, subif_r1)
    assert "SW1" not in warnings("Create VLAN 20 named IT on sw1", vlan_sw1, subif_r1).split(":")[0]
    # Any language: only the device names are compared
    assert "you didn't name R1" in warnings("اعمل VLAN 20 على sw1", vlan_sw1, subif_r1)
    # No warning: every changed device is named, no device named at all, or only a check on another one
    assert "didn't name" not in warnings("VLAN 20 on sw1 and a sub-interface on R1", vlan_sw1, subif_r1)
    assert "didn't name" not in warnings("Configure VLAN 20 everywhere", vlan_sw1, subif_r1)
    assert "didn't name" not in warnings("Create VLAN 20 on sw1 and test it", vlan_sw1,
                                         change("R1", ["ping 10.0.0.2"], [], type="check"))
    # "R1" inside another word is not R1
    assert "you didn't name R1" in warnings("Create VLAN 20 on sw1 (not on R10)", vlan_sw1, subif_r1)


def test_switch_commands_on_a_router_are_refused(kb):
    def errors(device, commands):
        return " ".join(validate({"changes": [change(device, commands, ["x"])]}, kb)["errors"])

    # The AI's real mistake: a trunk on router R2's Ethernet port
    kb.add_device({"name": "R2", "ip": "10.0.0.3", "vendor": "simulated", "state": "up"})
    assert "'switchport mode trunk' is a switch command, but R2 is a router" in errors(
        "R2", ["interface Ethernet0/0", "switchport mode trunk", "switchport trunk allowed vlan add 10"])
    for command in ("vlan 10", "spanning-tree vlan 1 priority 4096", "interface Vlan10"):
        assert "is a switch command" in errors("R1", [command]), command
    # Fine: router commands on a router, switch commands on a switch, and a router-like name
    # that "Find links" showed to be a switch (it answered with its VLANs)
    assert errors("R1", ["interface Ethernet0/0.10", "encapsulation dot1Q 10"]) == ""
    assert errors("SW1", ["vlan 10", "interface Ethernet0/1", "switchport access vlan 10"]) == ""
    kb.update_device("R2", vlans=["1 default"])
    assert errors("R2", ["switchport mode trunk"]) == ""


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


class HonestLLM:
    """First plan has an invalid VLAN; on the second try it refuses instead of guessing."""

    def __init__(self):
        self.requests = []

    def ask_json(self, system, user, schema):
        self.requests.append(user)
        if len(self.requests) == 1:
            return {"summary": "x", "changes": [change("SW1", ["vlan 5000"], ["no vlan 5000"])]}
        return {"summary": "VLAN 5000 can't be created: allowed VLANs are 1-4094.", "changes": []}


def test_ai_is_told_not_to_guess_the_users_values(kb):
    llm = HonestLLM()
    plan = pipeline.propose("create vlan 5000 on SW1", kb, llm)
    assert "do NOT change or guess" in llm.requests[1]  # the rule was sent with the errors
    assert "Do NOT suggest a different value" in llm.requests[1]  # no "use 10.1.1.1 instead"
    assert "1-4094" in llm.requests[1]                  # and the allowed range, so it can explain
    assert not plan["validation"]["ok"] and plan["id"] not in pipeline.PENDING  # nothing to approve
    assert "1-4094" in plan["summary"]


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


def change_management_ip(kb):
    """SW1 is reached on 10.0.0.2 (on Vlan1); the plan moves it to 10.0.0.50."""
    kb.update_device("SW1", interfaces=["Vlan1 10.0.0.2/24", "Ethernet0/1"])
    llm = FakeLLM({"summary": "x", "changes": [change(
        "SW1", ["interface Vlan1", "ip address 10.0.0.50 255.255.255.0"],
        ["interface Vlan1", "ip address 10.0.0.2 255.255.255.0"])]})
    return pipeline.approve(pipeline.propose("move SW1", kb, llm)["id"], kb)


def test_new_management_ip_is_saved_automatically(kb):
    result = change_management_ip(kb)  # a simulated device: the change just works
    assert result["success"] and "now reached on 10.0.0.50" in result["results"][0]["output"]
    assert kb.get_device("SW1")["ip"] == "10.0.0.50"
    assert kb.get_device("SW1")["interfaces"] == ["Vlan1 10.0.0.50/24", "Ethernet0/1"]


class DroppingDriver:
    """A real device: changing the IP we are connected to drops our SSH session."""
    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False

    def get_config(self):
        return "hostname SW1"

    def send_config(self, commands):
        raise ConnectionError("Socket is closed")


def test_dropped_connection_is_ok_if_the_new_ip_answers(kb, monkeypatch):
    from ibn.control import controller
    monkeypatch.setattr(controller, "get_driver", lambda device: DroppingDriver())
    monkeypatch.setattr(controller, "ping", lambda ip: ip == "10.0.0.50")  # answers on the new IP
    result = change_management_ip(kb)
    assert result["success"] and "dropped" in result["results"][0]["output"]
    assert kb.get_device("SW1")["ip"] == "10.0.0.50"


def test_dropped_connection_fails_if_the_new_ip_is_silent(kb, monkeypatch):
    from ibn.control import controller
    monkeypatch.setattr(controller, "get_driver", lambda device: DroppingDriver())
    monkeypatch.setattr(controller, "ping", lambda ip: False)  # nobody answers on the new IP
    result = change_management_ip(kb)
    assert not result["success"] and result["results"][0]["status"] == "failed"
    assert kb.get_device("SW1")["ip"] == "10.0.0.2"  # we don't save an IP that doesn't work


def test_rollback_moves_the_device_back_to_its_old_ip(kb):
    # SW1 moves to 10.0.0.50, then R1 fails: the rollback puts 10.0.0.2 back on SW1,
    # and the program must go back to 10.0.0.2 too (not keep the new IP).
    kb.update_device("SW1", interfaces=["Vlan1 10.0.0.2/24", "Ethernet0/1"])
    llm = FakeLLM({"summary": "x", "changes": [
        change("SW1", ["interface Vlan1", "ip address 10.0.0.50 255.255.255.0"],
               ["interface Vlan1", "ip address 10.0.0.2 255.255.255.0"]),
        change("R1", ["this is invalid"], ["no shutdown"]),
    ]})
    result = pipeline.approve(pipeline.propose("move SW1, break R1", kb, llm)["id"], kb)
    assert not result["success"]
    assert ("SW1", "rolled back") in [(r["device"], r["status"]) for r in result["results"]]
    assert kb.get_device("SW1")["ip"] == "10.0.0.2"
    assert kb.get_device("SW1")["interfaces"] == ["Vlan1 10.0.0.2/24", "Ethernet0/1"]


def test_rollback_follows_a_real_device_back_to_its_old_ip(kb, monkeypatch):
    # Real devices: every send drops the connection (R1's too, so R1 fails and we roll back).
    # SW1 answers on the new IP, then (after the rollback) on the old one.
    from ibn.control import controller
    monkeypatch.setattr(controller, "get_driver", lambda device: DroppingDriver())
    monkeypatch.setattr(controller, "ping", lambda ip: ip in ("10.0.0.50", "10.0.0.2"))
    kb.update_device("SW1", interfaces=["Vlan1 10.0.0.2/24"])
    llm = FakeLLM({"summary": "x", "changes": [
        change("SW1", ["interface Vlan1", "ip address 10.0.0.50 255.255.255.0"],
               ["interface Vlan1", "ip address 10.0.0.2 255.255.255.0"]),
        change("R1", ["hostname R1-new"], ["hostname R1"]),
    ]})
    result = pipeline.approve(pipeline.propose("move SW1, rename R1", kb, llm)["id"], kb)
    statuses = [(r["device"], r["status"]) for r in result["results"]]
    assert ("SW1", "applied") in statuses and ("R1", "failed") in statuses
    assert ("SW1", "rolled back") in statuses
    assert kb.get_device("SW1")["ip"] == "10.0.0.2"


def test_dry_run_does_not_move_the_device(kb, monkeypatch):
    from ibn import settings
    monkeypatch.setattr(settings, "DRY_RUN", True)
    assert change_management_ip(kb)["success"]
    assert kb.get_device("SW1")["ip"] == "10.0.0.2"  # nothing was sent, so nothing moved


def test_approved_warnings_are_saved_in_the_history(kb):
    # VLAN 10 is "HR"; renaming it gives a warning; the user approves anyway
    kb.record_change("SW1", {"time": "2020-01-01T10:00:00", "type": "config", "success": True,
                             "commands": ["vlan 10", "name HR"]})
    llm = FakeLLM({"summary": "x", "changes": [change("SW1", ["vlan 10", "name Sales"], ["vlan 10", "name HR"]),
                                              change("R1", ["hostname R1"], ["hostname R1"])]})
    plan = pipeline.propose("Create VLAN 10 named Sales on SW1 and R1", kb, llm)
    assert pipeline.approve(plan["id"], kb)["success"]
    sw1, r1 = kb.get_history("SW1")[-1], kb.get_history("R1")[-1]
    assert sw1["warnings"] == ["SW1: VLAN 10 already exists on SW1 as 'HR': this plan renames it to 'Sales'"]
    assert r1["warnings"] == []  # each device keeps only its own warnings


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


def test_cisco_interfaces_are_read_with_their_mask():
    output = """Ethernet0/0 is up, line protocol is up
  Internet address is 10.1.2.1/24
  Broadcast address is 255.255.255.255
Ethernet0/1 is administratively down, line protocol is down
  Internet protocol processing disabled
Loopback0 is up, line protocol is up
  Internet address is 10.0.0.1/32
  Secondary address 10.9.9.9/24"""
    assert get_vendor("cisco_ios").show_interfaces == "show ip interface"
    assert get_vendor("cisco_ios").parse_interfaces(output) == [
        "Ethernet0/0 10.1.2.1/24", "Ethernet0/1 unassigned", "Loopback0 10.0.0.1/32"]


def test_vlans_are_read_from_real_switches_and_nxos_interfaces_still_work():
    output = """VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Et0/0, Et0/1, Et0/2
                                                Et0/3
10   HR                               active
1002 fddi-default                     act/unsup"""
    for vendor in ("cisco_ios", "cisco_nxos", "arista_eos"):
        assert get_vendor(vendor).show_vlans == "show vlan brief"
        assert get_vendor(vendor).parse_vlans(output) == ["1 default", "10 HR", "1002 fddi-default"]
    assert get_vendor("cisco_ios").parse_vlans("% Invalid input detected at '^' marker.") == []  # a router
    # NX-OS prints "show ip interface" differently: it keeps the brief table
    nxos = get_vendor("cisco_nxos")
    assert nxos.show_interfaces == "show ip interface brief"
    assert nxos.parse_interfaces("Ethernet1/1     10.1.1.1        protocol-up/link-up/admin-up") == [
        "Ethernet1/1 10.1.1.1"]


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
    r1 = next(d for d in page_devices if d["name"] == "R1")
    assert r1["has_username"] is True and "username" not in r1  # the username is hidden too
    # editing without touching the hidden username (the page doesn't send it) keeps it
    client.post("/api/devices", json={"name": "R1", "ip": "10.0.0.1", "password": "newer"})
    assert kb.get_device("R1")["username"] == "admin" and kb.get_device("R1")["password"] == "newer"


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


def test_interfaces_can_be_typed_for_a_device(kb):
    """For devices Find links can't read (e.g. simulated): the AI needs their interfaces for routing."""
    client = create_app(kb, FakeLLM({})).test_client()
    client.post("/api/devices", json={"name": "R9", "ip": "10.9.9.9", "vendor": "simulated",
                                      "interfaces": "e0/0 192.168.1.1/24\n\n  Ethernet0/1   10.0.12.1/24 \nlo0 9.9.9.9"})
    assert kb.get_device("R9")["interfaces"] == ["Ethernet0/0 192.168.1.1/24", "Ethernet0/1 10.0.12.1/24",
                                                 "Loopback0 9.9.9.9"]
    client.post("/api/devices", json={"name": "R9", "ip": "10.9.9.9", "vendor": "simulated", "interfaces": ""})
    assert "interfaces" not in kb.get_device("R9")  # box emptied in Edit = no interfaces
    client.post("/api/devices", json={"name": "R9", "ip": "10.9.9.9", "vendor": "simulated"})  # no box: nothing changes
    assert "interfaces" not in kb.get_device("R9")
