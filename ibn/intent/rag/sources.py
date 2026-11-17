"""Knowledge sources. Each source turns its files into CHUNKS:
    {"source": "examples", "vendor": "cisco_ios", "search": text it is found by, "text": text for the prompt}

To add a source (e.g. command notes or Cisco doc chunks): write a class with a name, a title
and chunks(vendor), and add it to SOURCES at the bottom. Nothing else changes.
The files live in each vendor's own folder: ibn/vendors/<vendor>/ (next to its profile.py).
"""
import json
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


SOURCES = {source.name: source for source in (ExamplesSource(),)}
