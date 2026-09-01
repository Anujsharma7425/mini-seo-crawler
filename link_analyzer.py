"""Internal/external link analysis."""
from __future__ import annotations

from collections import Counter
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup


def analyze_links(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    page_host = urlsplit(page_url).hostname

    internal = []
    external = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(page_url, href)
        host = urlsplit(absolute).hostname

        if host == page_host:
            internal.append(absolute)
        else:
            external.append(absolute)

    return {
        "internal_link_count": len(internal),
        "external_link_count": len(external),
        "unique_internal_link_count": len(set(internal)),
        "unique_external_link_count": len(set(external)),
        "internal_links": list(dict.fromkeys(internal)),
        "external_links": list(dict.fromkeys(external)),
        "internal_duplicate_link_count": len(internal) - len(set(internal)),
        "anchor_summary": Counter(internal),
    }
