"""Shared component: the Knowledge Base (the system's memory of the network)."""
from .. import settings
from .base import KnowledgeBase


def get_knowledge_base() -> KnowledgeBase:
    """Pick the storage backend from settings. Add new backends here."""
    if settings.KB_BACKEND == "neo4j":
        from .neo4j_graph import Neo4jGraph
        return Neo4jGraph(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    from .file_graph import FileGraph
    return FileGraph(settings.KB_FILE)
