"""Hreflang analysis utilities."""
from __future__ import annotations

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup


LANG_RE = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2}|-[0-9]{3})?$")


def analyze_hreflang(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    tags = []
    errors = []

    for link in soup.find_all("link", rel=lambda x: x and "alternate" in x):
        hreflang = (link.get("hreflang") or "").strip()
        href = (link.get("href") or "").strip()
        if not hreflang or not href:
            continue

        absolute = urljoin(page_url, href)
        tags.append({"hreflang": hreflang, "href": absolute})

        if hreflang != "x-default" and not LANG_RE.match(hreflang):
            errors.append(f"Invalid hreflang value: {hreflang}")

    languages = [item["hreflang"] for item in tags]
    has_self_reference = page_url in {item["href"] for item in tags}

    return {
        "hreflang_present": bool(tags),
        "hreflang_count": len(tags),
        "hreflang_languages": languages,
        "hreflang_has_x_default": "x-default" in languages,
        "hreflang_has_self_reference": has_self_reference,
        "hreflang_errors": errors,
        "hreflang_tags": tags,
    }
