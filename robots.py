"""robots.txt fetching, caching and permission checks."""

from __future__ import annotations

import threading
from typing import Dict, Optional
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests


class RobotsHandler:
    """Fetches and caches robots.txt per host.

    If robots.txt is missing or unreachable, crawling is allowed (the same
    behaviour as Googlebot for a 404 response).
    """

    def __init__(self, user_agent: str, timeout: float = 10.0, enabled: bool = True) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.enabled = enabled
        self._cache: Dict[str, Optional[RobotFileParser]] = {}
        self._lock = threading.Lock()

    def _robots_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    def _get_parser(self, url: str) -> Optional[RobotFileParser]:
        robots_url = self._robots_url(url)
        with self._lock:
            if robots_url in self._cache:
                return self._cache[robots_url]

        parser: Optional[RobotFileParser] = None
        try:
            response = requests.get(
                robots_url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 200 and response.text.strip():
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
        except requests.RequestException:
            parser = None

        with self._lock:
            self._cache[robots_url] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        if not self.enabled:
            return True
        parser = self._get_parser(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:  # pragma: no cover - defensive
            return True

    def crawl_delay(self, url: str) -> Optional[float]:
        """Crawl-delay declared for our user agent, if any."""
        if not self.enabled:
            return None
        parser = self._get_parser(url)
        if parser is None:
            return None
        try:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay is not None else None
        except Exception:  # pragma: no cover - defensive
            return None
