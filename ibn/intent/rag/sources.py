"""Knowledge sources. Each source turns its files into CHUNKS:
    {"source": "docs", "vendor": "cisco_ios", "search": text it is found by, "text": text for the prompt}

Sources today:
    docs   ibn/vendors/<vendor>/docs/*.md and *.txt   notes WITH solved examples, one piece per "## " heading
To add a source: write a class with a name, a title and chunks(vendor), and add it to SOURCES at the
bottom. Nothing else changes. All files live in each vendor's own folder: ibn/vendors/<vendor>/.

The format of a .md doc (docs/README.md explains it for the team):
    ## Static route to a network                     <- one heading = one piece the AI can get
    Syntax: ip route <network> <mask> <next hop>     <- a short note
    Example: on R1 add a static route to 192.168.2.0/24 via R2
        Plan: Static route on R1 through R2           <- optional one-line summary
        R1 config:                                    <- "<device> config:", "undo:" or "check:"
            ip route 192.168.2.0 255.255.255.0 10.0.12.2
        R1 undo:
            no ip route 192.168.2.0 255.255.255.0 10.0.12.2
    Example: restart R2
        Refuse: reloading a device is blocked         <- a request that must be refused
"""
import re
from pathlib import Path

VENDORS_DIR = Path(__file__).resolve().parents[2] / "vendors"
# A vendor that uses another vendor's knowledge (the simulated device acts like Cisco IOS).
SAME_KNOWLEDGE_AS = {"simulated": "cisco_ios"}


def vendor_folder(vendor: str) -> Path:
    return VENDORS_DIR / SAME_KNOWLEDGE_AS.get(vendor, vendor)


class DocsSource:
    """Vendor notes with solved examples: ibn/vendors/<vendor>/docs/*.md (our own, cut at each
    "## " heading) and *.txt (pasted vendor pages, cut into pieces of about MAX_CHARS)."""
    name = "docs"
    title = "Vendor notes and solved examples (copy the method, not the names or addresses)"
    MAX_CHARS = 1200  # about 300 tokens per piece of a pasted page

    def chunks(self, vendor: str) -> list[dict]:
        folder = vendor_folder(vendor) / "docs"
        files = sorted(p for p in folder.glob("*") if p.suffix in (".txt", ".md") and p.name != "README.md")
        chunks = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for heading, body in sections(text) if path.suffix == ".md" else []:
                # Found by its heading + its example requests (request-to-request is the most precise),
                # or by the whole note when it has no examples.
                requests = [e["intent"] for e in read_examples(body)]
                search = "\n".join([heading] + requests) if requests else f"{heading}\n{body}"
                chunks.append({"source": self.name, "vendor": vendor, "search": search,
                               "text": f"[{path.stem}] {heading}\n{body}"})
            if path.suffix == ".txt" or not sections(text):  # pasted page, or notes without headings
                for piece in split_text(text, self.MAX_CHARS):
                    chunks.append({"source": self.name, "vendor": vendor, "search": piece,
                                   "text": f"[{path.stem}]\n{piece}"})
        return chunks


def sections(text: str) -> list[tuple[str, str]]:
    """ "## heading" + the lines under it, for each heading of a .md file."""
    found = re.split(r"^## +(.+)$", text, flags=re.MULTILINE)
    return [(found[i].strip(), found[i + 1].strip()) for i in range(1, len(found), 2)]


def read_examples(body: str) -> list[dict]:
    """The examples of one section, as plans: [{"intent": request, "plan": {"summary", "changes"}}].
    Used to build the search text, and by the tests to check every example."""
    examples, step = [], None
    for line in body.splitlines():
        if line.startswith("Example:"):
            examples.append({"intent": line[len("Example:"):].strip(), "plan": {"summary": "", "changes": []}})
            step = None
            continue
        if not examples:
            continue  # the note above the first example
        plan = examples[-1]["plan"]
        header = re.match(r"^ {4}(\S+) (config|undo|check):\s*$", line)
        if header:
            device, kind = header[1], header[2]
            if kind == "undo":  # the undo of this device's last config step
                step = next((c for c in reversed(plan["changes"]) if c["device"] == device), None)
                step = step["rollback"] if step is not None else None
            else:
                plan["changes"].append({"device": device, "type": kind, "commands": [], "rollback": []})
                step = plan["changes"][-1]["commands"]
        elif re.match(r"^ {4}(Plan|Refuse): ", line):
            plan["summary"] = line.split(":", 1)[1].strip()
        elif line.startswith(" " * 8) and line.strip() and step is not None:
            step.append(line.strip())
    return examples


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


SOURCES = {source.name: source for source in (DocsSource(),)}
