"""The knowledge base inside Neo4j, a real graph database.

Open http://localhost:7474 after `docker compose up -d` and run
    MATCH (n) RETURN n
to SEE your network as a graph.
"""
import json

from neo4j import GraphDatabase

from .base import KnowledgeBase


class Neo4jGraph(KnowledgeBase):
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._run("CREATE CONSTRAINT device_name IF NOT EXISTS "
                  "FOR (d:Device) REQUIRE d.name IS UNIQUE")

    def _run(self, cypher: str, **params) -> list[dict]:
        records, _, _ = self.driver.execute_query(cypher, **params)
        return [r.data() for r in records]

    # ---- devices ----
    def add_device(self, device):
        self._run("MERGE (d:Device {name: $name}) SET d += $props",
                  name=device["name"], props=device)

    def get_device(self, name):
        rows = self._run("MATCH (d:Device {name: $name}) RETURN d", name=name)
        return rows[0]["d"] if rows else None

    def list_devices(self):
        return [r["d"] for r in self._run("MATCH (d:Device) RETURN d ORDER BY d.name")]

    def update_device(self, name, **fields):
        self._run("MATCH (d:Device {name: $name}) SET d += $fields", name=name, fields=fields)

    def delete_device(self, name):
        self._run("MATCH (d:Device {name: $name}) "
                  "OPTIONAL MATCH (d)-[:HAS_CHANGE]->(c:Change) DETACH DELETE d, c", name=name)

    # ---- links ----
    def add_link(self, a, b):
        self._run("MATCH (a:Device {name: $a}), (b:Device {name: $b}) "
                  "MERGE (a)-[:CONNECTED_TO]-(b)", a=a, b=b)

    def list_links(self):
        # elementId(a) < elementId(b) so each link is returned once, not twice
        return self._run("MATCH (a:Device)-[:CONNECTED_TO]-(b:Device) "
                         "WHERE elementId(a) < elementId(b) RETURN a.name AS a, b.name AS b")

    # ---- history ----
    def record_change(self, device_name, change):
        # Neo4j properties can't hold nested lists/dicts, so we store the change as JSON text.
        self._run("MATCH (d:Device {name: $name}) "
                  "CREATE (d)-[:HAS_CHANGE]->(:Change {time: $time, data: $data})",
                  name=device_name, time=change.get("time", ""), data=json.dumps(change))

    def get_history(self, device_name):
        rows = self._run("MATCH (:Device {name: $name})-[:HAS_CHANGE]->(c:Change) "
                         "RETURN c.data AS data ORDER BY c.time", name=device_name)
        return [json.loads(r["data"]) for r in rows]
