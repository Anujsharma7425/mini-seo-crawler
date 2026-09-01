"""Sitemap discovery utilities for Mini SEO Crawler V2."""
from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


def _fetch(url: str, timeout: int = 15) -> bytes:
    req = Request(url, headers={"User-Agent": "MiniSEOCrawler/2.0"})
    with urlopen(req, timeout=timeout) as response:
        data = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def discover_sitemap_urls(base_url: str, timeout: int = 15) -> list[str]:
    """Try common sitemap locations and return discovered URLs."""
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    candidates = [
        urljoin(root, "/sitemap.xml"),
        urljoin(root, "/sitemap_index.xml"),
    ]

    found: list[str] = []
    seen_sitemaps: set[str] = set()

    def parse_sitemap(sitemap_url: str) -> None:
        if sitemap_url in seen_sitemaps:
            return
        seen_sitemaps.add(sitemap_url)

        try:
            xml = _fetch(sitemap_url, timeout)
            root_node = ET.fromstring(xml)
        except Exception:
            return

        for node in root_node.iter():
            tag = node.tag.split("}")[-1]
            if tag != "loc" or not node.text:
                continue

            loc = node.text.strip()
            parent_tag = ""
            # ElementTree does not expose parent directly, so infer from the
            # root type: sitemapindex contains sitemap children; urlset contains urls.
            if root_node.tag.split("}")[-1] == "sitemapindex":
                parse_sitemap(loc)
            else:
                if loc.startswith(("http://", "https://")):
                    found.append(loc)

    for candidate in candidates:
        parse_sitemap(candidate)

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(found))
