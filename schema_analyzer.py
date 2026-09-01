"""Basic JSON-LD / Schema.org analyzer."""
from __future__ import annotations

import json
from bs4 import BeautifulSoup


def analyze_schema(html: str) -> dict:
    """Extract JSON-LD blocks and report detected @type values."""
    soup = BeautifulSoup(html or "", "html.parser")
    blocks = []
    types = []
    errors = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue

        try:
            data = json.loads(raw)
            blocks.append(data)

            def collect_types(obj):
                if isinstance(obj, dict):
                    if "@type" in obj:
                        value = obj["@type"]
                        if isinstance(value, list):
                            types.extend(str(x) for x in value)
                        else:
                            types.append(str(value))
                    for value in obj.values():
                        collect_types(value)
                elif isinstance(obj, list):
                    for item in obj:
                        collect_types(item)

            collect_types(data)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))

    return {
        "schema_present": bool(blocks),
        "schema_block_count": len(blocks),
        "schema_types": sorted(set(types)),
        "schema_jsonld_errors": errors,
    }
