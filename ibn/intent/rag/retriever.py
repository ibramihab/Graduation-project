"""Ask every enabled source (RAG_SOURCES) for its chunks, keep the closest ones, build the text.

    retrieve("on R3 add a route to 10.0.1.0/24", ["cisco_ios"])
        -> "Vendor notes and solved examples ...:\n\n[static_routes] Static route ..."   ("" = nothing found)
"""
from ... import settings
from .embedder import scores
from .sources import SOURCES


def retrieve(text: str, vendors) -> str:
    if not settings.RAG_ENABLED:
        return ""
    parts = []
    for name in settings.RAG_SOURCES:
        source = SOURCES.get(name)
        if not source:
            print(f"RAG: unknown source '{name}' in RAG_SOURCES (known: {', '.join(SOURCES)})")
            continue
        chunks = [c for vendor in dict.fromkeys(v for v in vendors if v) for c in source.chunks(vendor)]
        best = closest(text, chunks, settings.RAG_TOP_K)
        if best:
            parts.append(f"{source.title}:\n\n" + "\n\n".join(c["text"] for c in best))
    return "\n\n".join(parts)


def closest(text: str, chunks: list[dict], how_many: int) -> list[dict]:
    if not chunks or how_many <= 0:
        return []
    ranked = sorted(zip(scores(text, [c["search"] for c in chunks]), range(len(chunks))), reverse=True)
    return [chunks[i] for score, i in ranked[:how_many] if score > 0]
