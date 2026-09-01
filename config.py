"""Configuration objects for the Mini SEO Crawler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

DEFAULT_USER_AGENT = (
    "MiniSEOCrawler/1.0 (+https://github.com/your-username/mini-seo-crawler)"
)


@dataclass
class Thresholds:
    """SEO thresholds used when flagging issues.

    The defaults follow widely used pixel-to-character approximations for
    Google SERP truncation. They can be overridden from the CLI.
    """

    title_min: int = 30
    title_max: int = 60
    meta_desc_min: int = 70
    meta_desc_max: int = 160
    h1_max: int = 1
    min_word_count: int = 300
    slow_response: float = 2.0  # seconds


@dataclass
class CrawlConfig:
    """Everything the crawler needs to run."""

    start_url: str
    max_pages: int = 100
    max_depth: int = 10
    delay: float = 0.5
    workers: int = 5
    timeout: float = 15.0
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True
    include_subdomains: bool = False
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)

    def __post_init__(self) -> None:
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.workers < 1:
            raise ValueError("workers must be at least 1")
        if self.delay < 0:
            raise ValueError("delay cannot be negative")
