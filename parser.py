"""HTML parsing: turn a page's markup into structured on-page SEO data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from bs4 import BeautifulSoup

from .utils import count_words, is_same_site, normalize_url

NON_TEXT_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")


def make_soup(html: str) -> BeautifulSoup:
    """Parse HTML with lxml when available, falling back to the stdlib parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - only when lxml is missing
        return BeautifulSoup(html, "html.parser")


@dataclass
class PageSEO:
    """On-page SEO facts extracted from a single HTML document."""

    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    meta_robots: str = ""
    canonical: str = ""
    h1_list: List[str] = field(default_factory=list)
    h2_list: List[str] = field(default_factory=list)
    h3_list: List[str] = field(default_factory=list)
    lang: str = ""
    has_viewport: bool = False
    og_title: str = ""
    schema_types: List[str] = field(default_factory=list)
    hreflang_count: int = 0
    internal_links: Set[str] = field(default_factory=set)
    external_links: Set[str] = field(default_factory=set)
    nofollow_links: int = 0
    images_total: int = 0
    images_missing_alt: int = 0
    word_count: int = 0

    @property
    def h1_count(self) -> int:
        return len(self.h1_list)

    @property
    def h1(self) -> str:
        return self.h1_list[0] if self.h1_list else ""


def _clean(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _extract_schema_types(soup: BeautifulSoup) -> List[str]:
    """Collect @type values from JSON-LD blocks (best effort, no strict parsing)."""
    import json

    types: List[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                value = node.get("@type")
                if isinstance(value, str):
                    types.append(value)
                elif isinstance(value, list):
                    types.extend(str(v) for v in value)
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    # de-duplicate while keeping order
    seen, unique = set(), []
    for item in types:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def parse_page(html: str, page_url: str, root_url: str, include_subdomains: bool = False) -> PageSEO:
    """Extract every on-page element the report needs from ``html``."""
    seo = PageSEO()
    soup = make_soup(html)

    # --- title -----------------------------------------------------------
    if soup.title and soup.title.string:
        seo.title = _clean(soup.title.string)
    seo.title_length = len(seo.title)

    # --- meta tags -------------------------------------------------------
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower().strip()
        prop = (meta.get("property") or "").lower().strip()
        content = _clean(meta.get("content"))
        if name == "description" and not seo.meta_description:
            seo.meta_description = content
        elif name == "robots":
            seo.meta_robots = content.lower()
        elif name == "googlebot" and not seo.meta_robots:
            seo.meta_robots = content.lower()
        elif name == "viewport":
            seo.has_viewport = True
        elif prop == "og:title" and not seo.og_title:
            seo.og_title = content
    seo.meta_description_length = len(seo.meta_description)

    # --- html lang -------------------------------------------------------
    html_tag = soup.find("html")
    if html_tag:
        seo.lang = _clean(html_tag.get("lang"))

    # --- canonical & hreflang -------------------------------------------
    for link in soup.find_all("link", href=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        if "canonical" in rels and not seo.canonical:
            seo.canonical = normalize_url(link["href"], base=page_url) or ""
        if "alternate" in rels and link.get("hreflang"):
            seo.hreflang_count += 1

    # --- headings --------------------------------------------------------
    seo.h1_list = [_clean(t.get_text()) for t in soup.find_all("h1")]
    seo.h2_list = [_clean(t.get_text()) for t in soup.find_all("h2")]
    seo.h3_list = [_clean(t.get_text()) for t in soup.find_all("h3")]

    # --- structured data -------------------------------------------------
    seo.schema_types = _extract_schema_types(soup)

    # --- links -----------------------------------------------------------
    for anchor in soup.find_all("a", href=True):
        rels = " ".join(anchor.get("rel") or []).lower()
        if "nofollow" in rels:
            seo.nofollow_links += 1
        target = normalize_url(anchor["href"], base=page_url)
        if not target:
            continue
        if is_same_site(target, root_url, include_subdomains):
            seo.internal_links.add(target)
        else:
            seo.external_links.add(target)

    # --- images ----------------------------------------------------------
    images = soup.find_all("img")
    seo.images_total = len(images)
    seo.images_missing_alt = sum(1 for img in images if not (img.get("alt") or "").strip())

    # --- visible word count ---------------------------------------------
    body = soup.body or soup
    for tag in body.find_all(NON_TEXT_TAGS):
        tag.decompose()
    seo.word_count = count_words(body.get_text(" ", strip=True))

    return seo
