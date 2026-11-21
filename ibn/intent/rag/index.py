"""The saved numbers (vectors) of every text, so each text is sent to the embedding model only once.
Stored in data/rag_index.json (not on GitHub). A changed or new text is computed again by itself."""
import hashlib
import json
import os

INDEX_FILE = "data/rag_index.json"


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def vectors(texts: list[str], model: str, embed) -> list[list[float]]:
    """The vectors of these texts; only the ones not saved yet are computed (with embed)."""
    try:
        with open(INDEX_FILE, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {}
    saved = index.setdefault(model, {})
    missing = list(dict.fromkeys(t for t in texts if _key(t) not in saved))
    if missing:
        for text, vector in zip(missing, embed(missing)):
            saved[_key(text)] = vector
        os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f)
    return [saved[_key(t)] for t in texts]
