"""Knowledge sources. Each source turns its files into CHUNKS:
    {"source": "examples", "vendor": "cisco_ios", "search": text it is found by, "text": text for the prompt}

Sources today:
    examples   ibn/vendors/<vendor>/examples.json   solved requests
    docs       ibn/vendors/<vendor>/docs/*.txt       vendor documentation, cut into small pieces
To add a source (e.g. command notes): write a class with a name, a title and chunks(vendor),
and add it to SOURCES at the bottom. Nothing else changes.
All files live in each vendor's own folder: ibn/vendors/<vendor>/ (next to its profile.py).
"""
import json
import re
from pathlib import Path

VENDORS_DIR = Path(__file__).resolve().parents[2] / "vendors"
# A vendor that uses another vendor's knowledge (the simulated device acts like Cisco IOS).
SAME_KNOWLEDGE_AS = {"simulated": "cisco_ios"}


def vendor_folder(vendor: str) -> Path:
    return VENDORS_DIR / SAME_KNOWLEDGE_AS.get(vendor, vendor)


class ExamplesSource:
    """Solved requests: ibn/vendors/<vendor>/examples.json -> found by the request text."""
    name = "examples"
    title = "Similar requests that were solved correctly"

    def chunks(self, vendor: str) -> list[dict]:
        path = vendor_folder(vendor) / "examples.json"
        if not path.exists():
            return []
        chunks = []
        for example in json.loads(path.read_text(encoding="utf-8")):
            text = f'Request: "{example["intent"]}"\n{json.dumps(example["plan"], ensure_ascii=False)}'
            chunks.append({"source": self.name, "vendor": vendor, "search": example["intent"], "text": text})
        return chunks


class DocsSource:
    """Vendor documentation: ibn/vendors/<vendor>/docs/*.txt or *.md (e.g. Cisco guide pages saved
    as text). Long files are cut into pieces of about MAX_CHARS, so only the relevant parts are sent."""
    name = "docs"
    title = "Relevant parts of the vendor documentation"
    MAX_CHARS = 1200  # about 300 tokens per piece

    def chunks(self, vendor: str) -> list[dict]:
        folder = vendor_folder(vendor) / "docs"
        files = sorted(p for p in folder.glob("*") if p.suffix in (".txt", ".md") and p.name != "README.md")
        chunks = []
        for path in files:
            for piece in split_text(path.read_text(encoding="utf-8", errors="ignore"), self.MAX_CHARS):
                chunks.append({"source": self.name, "vendor": vendor, "search": piece,
                               "text": f"[{path.stem}]\n{piece}"})
        return chunks


def split_text(text: str, max_chars: int) -> list[str]:
    """Cut a long text into pieces of at most max_chars, at blank lines (paragraphs) when possible."""
    pieces, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if len(paragraph) > max_chars and current:  # keep the order: save what we have first
            pieces.append(current)
            current = ""
        while len(paragraph) > max_chars:  # a very long paragraph: cut it at a line end
            cut = paragraph.rfind("\n", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            pieces.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + len(paragraph) + 2 > max_chars:
            pieces.append(current)
            current = ""
        if paragraph:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


SOURCES = {source.name: source for source in (ExamplesSource(), DocsSource())}
