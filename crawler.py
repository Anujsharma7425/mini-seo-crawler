"""The crawl engine: breadth-first discovery of internal URLs."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Set, Tuple

from .analyzer import PageResult, analyze
from .config import CrawlConfig
from .fetcher import Fetcher
from .parser import PageSEO, parse_page
from .robots import RobotsHandler
from .utils import RateLimiter, is_same_site, looks_like_file, matches_any, normalize_url

ProgressCallback = Callable[[int, int, PageResult], None]


class Crawler:
    """Crawl one website, breadth-first, and return analysed page data.

    The queue holds ``(url, depth)`` pairs. Each round pulls up to ``workers``
    URLs off the queue, fetches them in parallel, then pushes any newly found
    internal links back on. Crawling stops at ``max_pages``, at ``max_depth``
    or when the queue empties.
    """

    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.start_url = normalize_url(config.start_url)
        if not self.start_url:
            raise ValueError(f"Invalid start URL: {config.start_url!r}")

        self.fetcher = Fetcher(config.user_agent, timeout=config.timeout)
        self.robots = RobotsHandler(
            config.user_agent, timeout=config.timeout, enabled=config.respect_robots
        )
        delay = config.delay
        robots_delay = self.robots.crawl_delay(self.start_url)
        if robots_delay:
            delay = max(delay, robots_delay)
        self.limiter = RateLimiter(delay)

        self.visited: Set[str] = set()
        self.results: List[PageResult] = []
        self.skipped_external: Set[str] = set()

    # ------------------------------------------------------------------
    def _should_queue(self, url: str) -> bool:
        if url in self.visited:
            return False
        if not is_same_site(url, self.start_url, self.config.include_subdomains):
            self.skipped_external.add(url)
            return False
        if looks_like_file(url):
            return False
        if self.config.include_patterns and not matches_any(url, self.config.include_patterns):
            return False
        if self.config.exclude_patterns and matches_any(url, self.config.exclude_patterns):
            return False
        return True

    def _crawl_one(self, url: str, depth: int) -> PageResult:
        result = PageResult(url=url, depth=depth)

        if not self.robots.can_fetch(url):
            result.blocked_by_robots = True
            return result

        self.limiter.wait()
        fetched = self.fetcher.fetch(url)
        result.final_url = fetched.final_url
        result.status_code = fetched.status_code
        result.response_time = fetched.response_time
        result.content_type = fetched.content_type
        result.redirect_chain = fetched.redirect_chain
        result.x_robots_tag = fetched.x_robots_tag
        result.error = fetched.error

        if fetched.html:
            result.seo = parse_page(
                fetched.html,
                page_url=fetched.final_url or url,
                root_url=self.start_url,
                include_subdomains=self.config.include_subdomains,
            )
        else:
            result.seo = PageSEO()
        return result

    # ------------------------------------------------------------------
    def crawl(self, on_progress: Optional[ProgressCallback] = None) -> List[PageResult]:
        """Run the crawl and return analysed :class:`PageResult` objects."""
        queue: deque[Tuple[str, int]] = deque([(self.start_url, 0)])
        self.visited.add(self.start_url)

        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            while queue and len(self.results) < self.config.max_pages:
                batch: List[Tuple[str, int]] = []
                while queue and len(batch) < self.config.workers:
                    if len(self.results) + len(batch) >= self.config.max_pages:
                        break
                    batch.append(queue.popleft())

                for result in pool.map(lambda item: self._crawl_one(*item), batch):
                    self.results.append(result)
                    if on_progress:
                        on_progress(len(self.results), self.config.max_pages, result)

                    if result.depth >= self.config.max_depth:
                        continue
                    for link in sorted(result.seo.internal_links):
                        if len(self.visited) >= self.config.max_pages * 5:
                            break  # keep the frontier from exploding on huge sites
                        if self._should_queue(link):
                            self.visited.add(link)
                            queue.append((link, result.depth + 1))

        self.fetcher.close()
        return analyze(self.results, self.config.thresholds)

    # ------------------------------------------------------------------
    @property
    def queued_but_not_crawled(self) -> int:
        return max(0, len(self.visited) - len(self.results))
