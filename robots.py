"""robots.txt handling for Mini SEO Crawler V2."""
from __future__ import annotations

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser


def load_robots(base_url: str, user_agent: str = "MiniSEOCrawler") -> RobotFileParser:
    """Load robots.txt for a site."""
    robots_url = urljoin(base_url.rstrip("/") + "/", "robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        # An unavailable robots.txt should not crash the crawler.
        pass
    return parser


def can_fetch(parser: RobotFileParser, url: str, user_agent: str = "MiniSEOCrawler") -> bool:
    """Return whether the URL is allowed for the crawler's user agent."""
    try:
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


def extract_sitemaps_from_robots(text: str) -> list[str]:
    """Extract Sitemap directives from robots.txt text."""
    result = []
    for line in text.splitlines():
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                result.append(value)
    return list(dict.fromkeys(result))
