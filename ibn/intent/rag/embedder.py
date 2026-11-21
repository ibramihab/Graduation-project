"""How close is a text to the request? Two ways (RAG_SEARCH in .env):
    "embedding": an embedding model in Ollama (RAG_EMBED_MODEL, e.g. bge-m3) turns texts into
                 numbers; close numbers = close meaning, also across Arabic and English.
    "keyword":   count the words they share. No model needed.
If the embedding model can't be reached, the keyword way is used (the program never breaks).
"""
import math
import re

import requests

from ... import settings
from . import index

# Small words that appear in almost every request: they say nothing about the topic.
STOP_WORDS = {"a", "an", "the", "on", "in", "of", "to", "from", "for", "and", "or", "with", "is",
              "are", "it", "my", "i", "me", "we", "please", "can", "that", "this", "at", "by", "do"}


def scores(query: str, texts: list[str]) -> list[float]:
    """One score per text: higher = closer to the query."""
    if settings.RAG_SEARCH == "embedding":
        try:
            return embedding_scores(query, texts)
        except Exception as error:  # Ollama off or the model not downloaded
            print(f"RAG: embedding search not available ({error}); using keyword search.")
    return [keyword_score(query, t) for t in texts]


def embedding_scores(query: str, texts: list[str]) -> list[float]:
    saved = index.vectors(texts, settings.RAG_EMBED_MODEL, embed)
    wanted = embed([query])[0]
    return [cosine(wanted, v) for v in saved]


def embed(texts: list[str]) -> list[list[float]]:
    """Ask Ollama's embedding model for the numbers of each text."""
    response = requests.post(f"{settings.OLLAMA_URL}/api/embed", timeout=120,
                             json={"model": settings.RAG_EMBED_MODEL, "input": texts})
    response.raise_for_status()
    return response.json()["embeddings"]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def keyword_score(query: str, text: str) -> float:
    words = lambda s: set(re.findall(r"\w+", s.lower())) - STOP_WORDS
    q, t = words(query), words(text)
    return len(q & t) / math.sqrt(len(q) * len(t)) if q and t else 0.0
