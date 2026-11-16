"""RAG for the intent layer: find the knowledge closest to a request and add it to the prompt.

    sources.py    WHERE knowledge comes from (examples now; notes, docs... later)
    embedder.py   HOW "close" is measured (bge-m3 via Ollama, or shared words)
    index.py      the saved numbers of every text (computed once, in data/)
    retriever.py  asks every enabled source and builds the text for the prompt
"""
from .retriever import retrieve  # noqa: F401
