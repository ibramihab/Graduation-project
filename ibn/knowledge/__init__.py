"""Shared component: the Knowledge Base (the system's memory of the network)."""
from .. import settings
from . import graph_analysis
from .base import KnowledgeBase


def get_knowledge_base() -> KnowledgeBase:
    """The storage of the knowledge base: a JSON file (data/knowledge.json).
    Another storage (a database) can be added later: write a class that follows
    KnowledgeBase (base.py) and return it here. Nothing else changes."""
    from .file_graph import FileGraph
    return FileGraph(settings.KB_FILE)
