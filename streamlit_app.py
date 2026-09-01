"""Mini SEO Crawler - single-file version.

Everything (crawler + web UI) lives in this one file so it can be deployed by
uploading a single file. The full, properly structured version of this project
is at: https://github.com/Anujsharma7425/mini-seo-crawler

Run locally:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import io
import re
import threading
import time
from collections import Counter, OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "MiniSEOCrawler/1.0 (+https://github.com/Anujsharma7425/mini-seo-crawler)"

# ======================================================================
# 1. URL helpers
# ======================================================================

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "_ga", "yclid",
}

NON_HTML_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".avif",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".zip", ".rar", ".gz", ".tar", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".webm", ".ogg", ".wav",
    ".css", ".js", ".json", ".xml", ".rss", ".txt",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".exe", ".dmg", ".apk",
}

DEFAULT_PORTS = {"http": "80", "https": "443"}
_WORD_RE = re.compile(r"[A-Za-z0-9\u00C0-\u024F\u0900-\u097F']+")
_INVALID_HOST_CHARS = re.compile(r"[\s<>\"'`\\|^{}\[\]()]")
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def is_valid_host(host: str) -> bool:
    if not host or _INVALID_HOST_CHARS.search(host):
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if ":" in host or _IPV4_RE.fullmatch(host):
        return True
    return "." in host and not host.startswith(".") and not host.endswith(".")


def normalize_url(url: str, base: Optional[str] = None) -> Optional[str]:
    """Canonical, comparable form of a URL so the same page is never crawled twice."""
    if not url:
        return None
    url = url.strip().replace("\n", "").replace("\t", "")
    if not url or url.startswith(("javascript:", "mailto:", "tel:", "#", "data:", "sms:")):
        return None
    if base:
        url = urljoin(base, url)

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None

    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if not is_valid_host(hostname):
        return None

    netloc = hostname
    if parts.port and str(parts.port) != DEFAULT_PORTS.get(scheme):
        netloc = f"{hostname}:{parts.port}"

    pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(sorted(pairs), doseq=True), ""))


def get_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(url: str, root_url: str, include_subdomains: bool = False) -> bool:
    host, root = get_host(url), get_host(root_url)
    if not host or not root:
        return False
    if host == root:
        return True
    return include_subdomains and host.endswith("." + root)


def looks_like_file(url: str) -> bool:
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    return dot != -1 and path[dot:] in NON_HTML_EXTENSIONS


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def truncate(value: Optional[str], limit: int = 300) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "\u2026"


class RateLimiter:
    """One delay budget shared by every worker thread."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = max(0.0, delay)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_allowed - now)
            self._next_allowed = now + sleep_for + self.delay
        if sleep_for:
            time.sleep(sleep_for)


# ======================================================================
# 2. robots.txt
# ======================================================================

class RobotsHandler:
    def __init__(self, user_agent: str, timeout: float = 10.0, enabled: bool = True) -> None:
        self.user_agent, self.timeout, self.enabled = user_agent, timeout, enabled
        self._cache: Dict[str, Optional[RobotFileParser]] = {}
        self._lock = threading.Lock()

    def _get_parser(self, url: str) -> Optional[RobotFileParser]:
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        with self._lock:
            if robots_url in self._cache:
                return self._cache[robots_url]
        parser = None
        try:
            response = requests.get(robots_url, timeout=self.timeout,
                                    headers={"User-Agent": self.user_agent})
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
        except Exception:
            return True

    def crawl_delay(self, url: str) -> Optional[float]:
        if not self.enabled:
            return None
        parser = self._get_parser(url)
        if parser is None:
            return None
        try:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay is not None else None
        except Exception:
            return None


# ======================================================================
# 3. HTTP fetching
# ======================================================================

MAX_BYTES = 3 * 1024 * 1024


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status_code: Optional[int] = None
    response_time: float = 0.0
    content_type: str = ""
    html: Optional[str] = None
    redirect_chain: List[int] = field(default_factory=list)
    x_robots_tag: str = ""
    error: str = ""

    @property
    def is_html(self) -> bool:
        return "html" in (self.content_type or "").lower()


class Fetcher:
    def __init__(self, user_agent: str, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "HEAD"]), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self, url: str) -> FetchResult:
        result = FetchResult(url=url, final_url=url)
        started = time.perf_counter()
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
            result.status_code = response.status_code
            result.final_url = response.url
            result.content_type = response.headers.get("Content-Type", "")
            result.x_robots_tag = response.headers.get("X-Robots-Tag", "")
            result.redirect_chain = [r.status_code for r in response.history]
            if result.is_html:
                content = response.raw.read(MAX_BYTES, decode_content=True) or b""
                encoding = response.encoding or response.apparent_encoding or "utf-8"
                result.html = content.decode(encoding, errors="replace")
            response.close()
        except requests.exceptions.Timeout:
            result.error = "TIMEOUT"
        except requests.exceptions.TooManyRedirects:
            result.error = "TOO_MANY_REDIRECTS"
        except requests.exceptions.SSLError:
            result.error = "SSL_ERROR"
        except requests.exceptions.ConnectionError:
            result.error = "CONNECTION_ERROR"
        except requests.RequestException as exc:
            result.error = f"REQUEST_ERROR: {exc.__class__.__name__}"
        except Exception as exc:
            result.error = f"UNEXPECTED_ERROR: {exc.__class__.__name__}"
        finally:
            result.response_time = round(time.perf_counter() - started, 3)
        return result

    def close(self) -> None:
        self.session.close()


# ======================================================================
# 4. HTML parsing
# ======================================================================

NON_TEXT_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")


@dataclass
class PageSEO:
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    meta_robots: str = ""
    canonical: str = ""
    h1_list: List[str] = field(default_factory=list)
    h2_list: List[str] = field(default_factory=list)
    lang: str = ""
    has_viewport: bool = False
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


def _schema_types(soup: BeautifulSoup) -> List[str]:
    import json
    types: List[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
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
    seen, unique = set(), []
    for item in types:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def parse_page(html: str, page_url: str, root_url: str, include_subdomains: bool = False) -> PageSEO:
    seo = PageSEO()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    if soup.title and soup.title.string:
        seo.title = _clean(soup.title.string)
    seo.title_length = len(seo.title)

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower().strip()
        content = _clean(meta.get("content"))
        if name == "description" and not seo.meta_description:
            seo.meta_description = content
        elif name == "robots":
            seo.meta_robots = content.lower()
        elif name == "googlebot" and not seo.meta_robots:
            seo.meta_robots = content.lower()
        elif name == "viewport":
            seo.has_viewport = True
    seo.meta_description_length = len(seo.meta_description)

    html_tag = soup.find("html")
    if html_tag:
        seo.lang = _clean(html_tag.get("lang"))

    for link in soup.find_all("link", href=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        if "canonical" in rels and not seo.canonical:
            seo.canonical = normalize_url(link["href"], base=page_url) or ""
        if "alternate" in rels and link.get("hreflang"):
            seo.hreflang_count += 1

    seo.h1_list = [_clean(t.get_text()) for t in soup.find_all("h1")]
    seo.h2_list = [_clean(t.get_text()) for t in soup.find_all("h2")]
    seo.schema_types = _schema_types(soup)

    for anchor in soup.find_all("a", href=True):
        if "nofollow" in " ".join(anchor.get("rel") or []).lower():
            seo.nofollow_links += 1
        target = normalize_url(anchor["href"], base=page_url)
        if not target:
            continue
        if is_same_site(target, root_url, include_subdomains):
            seo.internal_links.add(target)
        else:
            seo.external_links.add(target)

    images = soup.find_all("img")
    seo.images_total = len(images)
    seo.images_missing_alt = sum(1 for img in images if not (img.get("alt") or "").strip())

    body = soup.body or soup
    for tag in body.find_all(NON_TEXT_TAGS):
        tag.decompose()
    seo.word_count = count_words(body.get_text(" ", strip=True))
    return seo


# ======================================================================
# 5. Analysis: indexability, issues, duplicates
# ======================================================================

CRITICAL, HIGH, MEDIUM, LOW = "Critical", "High", "Medium", "Low"
SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}

INDEXABLE = "Indexable"
NOINDEX = "Non-Indexable (noindex)"
REDIRECT = "Non-Indexable (redirect)"
CANONICALISED = "Non-Indexable (canonicalised)"
BLOCKED = "Non-Indexable (blocked by robots.txt)"
ERROR = "Non-Indexable (error)"
NON_HTML = "Non-Indexable (not HTML)"


@dataclass
class Thresholds:
    title_min: int = 30
    title_max: int = 60
    meta_desc_min: int = 70
    meta_desc_max: int = 160
    h1_max: int = 1
    min_word_count: int = 300
    slow_response: float = 2.0


@dataclass
class PageResult:
    url: str
    depth: int = 0
    final_url: str = ""
    status_code: Optional[int] = None
    response_time: float = 0.0
    content_type: str = ""
    error: str = ""
    redirect_chain: List[int] = field(default_factory=list)
    x_robots_tag: str = ""
    blocked_by_robots: bool = False
    seo: PageSEO = field(default_factory=PageSEO)
    indexability: str = ""
    indexability_reason: str = ""
    issues: List[str] = field(default_factory=list)
    duplicate_title: bool = False
    duplicate_meta_description: bool = False
    duplicate_h1: bool = False

    @property
    def is_indexable(self) -> bool:
        return self.indexability == INDEXABLE

    @property
    def canonical_status(self) -> str:
        if not self.seo.canonical:
            return "Missing"
        target = self.seo.canonical.rstrip("/")
        for candidate in (self.url, self.final_url):
            if candidate and target == candidate.rstrip("/"):
                return "Self-referencing"
        return "Points to another URL"

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def _has_directive(result: PageResult, directive: str) -> bool:
    directive = directive.lower()
    return (directive in (result.seo.meta_robots or "").lower()
            or directive in (result.x_robots_tag or "").lower())


def set_indexability(result: PageResult) -> None:
    if result.blocked_by_robots:
        result.indexability, result.indexability_reason = BLOCKED, "Disallowed in robots.txt"
    elif result.error:
        result.indexability, result.indexability_reason = ERROR, result.error
    elif result.status_code is None:
        result.indexability, result.indexability_reason = ERROR, "No response"
    elif result.status_code >= 400:
        result.indexability, result.indexability_reason = ERROR, f"HTTP {result.status_code}"
    elif result.redirect_chain or (300 <= result.status_code < 400):
        codes = result.redirect_chain or [result.status_code]
        result.indexability = REDIRECT
        result.indexability_reason = f"Redirected ({'>'.join(str(c) for c in codes)})"
    elif result.content_type and "html" not in result.content_type.lower():
        result.indexability, result.indexability_reason = NON_HTML, result.content_type
    elif _has_directive(result, "noindex"):
        result.indexability, result.indexability_reason = NOINDEX, "noindex directive"
    elif result.canonical_status == "Points to another URL":
        result.indexability = CANONICALISED
        result.indexability_reason = f"Canonical \u2192 {result.seo.canonical}"
    else:
        result.indexability, result.indexability_reason = INDEXABLE, ""


def detect_issues(result: PageResult, t: Thresholds) -> List[str]:
    issues: List[str] = []
    seo = result.seo

    if result.error:
        return [f"Request failed ({result.error})"]
    if result.status_code and result.status_code >= 500:
        return [f"Server error ({result.status_code})"]
    if result.status_code and 400 <= result.status_code < 500:
        return [f"Broken URL ({result.status_code})"]
    if result.blocked_by_robots:
        return ["Blocked by robots.txt"]
    if result.redirect_chain:
        issues.append(f"Redirected to {result.final_url}")
        if len(result.redirect_chain) > 1:
            issues.append(f"Redirect chain ({len(result.redirect_chain)} hops)")
    if result.content_type and "html" not in result.content_type.lower():
        return issues
    if result.response_time > t.slow_response:
        issues.append(f"Slow response ({result.response_time:.2f}s)")

    if _has_directive(result, "noindex"):
        issues.append("Noindex directive")
    if _has_directive(result, "nofollow"):
        issues.append("Page-level nofollow directive")

    if not seo.title:
        issues.append("Missing title")
    else:
        if seo.title_length < t.title_min:
            issues.append(f"Short title ({seo.title_length} chars)")
        elif seo.title_length > t.title_max:
            issues.append(f"Long title ({seo.title_length} chars)")
        if result.duplicate_title:
            issues.append("Duplicate title")

    if not seo.meta_description:
        issues.append("Missing meta description")
    else:
        if seo.meta_description_length < t.meta_desc_min:
            issues.append(f"Short meta description ({seo.meta_description_length} chars)")
        elif seo.meta_description_length > t.meta_desc_max:
            issues.append(f"Long meta description ({seo.meta_description_length} chars)")
        if result.duplicate_meta_description:
            issues.append("Duplicate meta description")

    if seo.h1_count == 0:
        issues.append("Missing H1")
    elif seo.h1_count > t.h1_max:
        issues.append(f"Multiple H1 tags ({seo.h1_count})")
    if result.duplicate_h1:
        issues.append("Duplicate H1")
    if seo.title and seo.h1 and seo.title.lower() == seo.h1.lower():
        issues.append("Title identical to H1")

    if result.canonical_status == "Missing":
        issues.append("Missing canonical")
    elif result.canonical_status == "Points to another URL":
        issues.append(f"Canonicalised to {seo.canonical}")

    if seo.word_count < t.min_word_count:
        issues.append(f"Low word count ({seo.word_count} words)")
    if seo.images_missing_alt:
        issues.append(f"{seo.images_missing_alt} image(s) missing ALT text")
    if not seo.has_viewport:
        issues.append("Missing viewport meta tag (mobile)")
    if not seo.lang:
        issues.append("Missing html lang attribute")
    if not seo.schema_types:
        issues.append("No structured data (JSON-LD) found")
    return issues


def _mark_duplicates(results: List[PageResult]) -> None:
    candidates = [r for r in results if r.status_code == 200 and not r.redirect_chain]

    def flag(getter, setter):
        counts = Counter()
        for result in candidates:
            value = getter(result)
            if value:
                counts[value.strip().lower()] += 1
        for result in candidates:
            value = getter(result)
            if value and counts[value.strip().lower()] > 1:
                setter(result)

    flag(lambda r: r.seo.title, lambda r: setattr(r, "duplicate_title", True))
    flag(lambda r: r.seo.meta_description, lambda r: setattr(r, "duplicate_meta_description", True))
    flag(lambda r: r.seo.h1, lambda r: setattr(r, "duplicate_h1", True))


def analyze(results: List[PageResult], thresholds: Thresholds) -> List[PageResult]:
    _mark_duplicates(results)
    for result in results:
        set_indexability(result)
        result.issues = detect_issues(result, thresholds)
    return results


def issue_severity(issue: str) -> str:
    lowered = issue.lower()
    if any(k in lowered for k in ("broken", "server error", "request failed", "blocked by robots")):
        return CRITICAL
    if any(k in lowered for k in ("noindex", "missing title", "missing h1", "canonicalised", "duplicate title")):
        return HIGH
    if any(k in lowered for k in ("missing meta description", "multiple h1", "missing canonical",
                                  "duplicate", "redirect", "alt text", "low word count", "slow response")):
        return MEDIUM
    return LOW


def build_summary(results: List[PageResult]) -> "OrderedDict[str, object]":
    buckets = Counter()
    for r in results:
        code = r.status_code
        if r.error or code is None:
            buckets["Failed / no response"] += 1
        elif 200 <= code < 300:
            buckets["2xx Success"] += 1
        elif 300 <= code < 400:
            buckets["3xx Redirect"] += 1
        elif 400 <= code < 500:
            buckets["4xx Client error"] += 1
        else:
            buckets["5xx Server error"] += 1

    html_pages = [r for r in results if r.status_code == 200 and not r.error]

    def count(predicate) -> int:
        return sum(1 for r in html_pages if predicate(r))

    s: "OrderedDict[str, object]" = OrderedDict()
    s["Pages crawled"] = len(results)
    for label in ("2xx Success", "3xx Redirect", "4xx Client error", "5xx Server error", "Failed / no response"):
        s[label] = buckets.get(label, 0)
    s["Indexable pages"] = sum(1 for r in results if r.is_indexable)
    s["Non-indexable pages"] = len(results) - s["Indexable pages"]
    s["Missing titles"] = count(lambda r: not r.seo.title)
    s["Duplicate titles"] = count(lambda r: r.duplicate_title)
    s["Titles too long"] = count(lambda r: r.seo.title_length > 60)
    s["Missing meta descriptions"] = count(lambda r: not r.seo.meta_description)
    s["Duplicate meta descriptions"] = count(lambda r: r.duplicate_meta_description)
    s["Missing H1"] = count(lambda r: r.seo.h1_count == 0)
    s["Multiple H1"] = count(lambda r: r.seo.h1_count > 1)
    s["Missing canonical"] = count(lambda r: r.canonical_status == "Missing")
    s["Canonicalised to another URL"] = count(lambda r: r.canonical_status == "Points to another URL")
    s["Noindex pages"] = count(lambda r: _has_directive(r, "noindex"))
    s["Images missing ALT (total)"] = sum(r.seo.images_missing_alt for r in html_pages)
    s["Thin pages (<300 words)"] = count(lambda r: r.seo.word_count < 300)
    s["Pages with structured data"] = count(lambda r: bool(r.seo.schema_types))
    s["Total issues found"] = sum(r.issue_count for r in results)
    if results:
        s["Average response time (s)"] = round(sum(r.response_time for r in results) / len(results), 3)
    return s


def health_score(results: List[PageResult]) -> int:
    if not results:
        return 0
    weights = {CRITICAL: 5, HIGH: 3, MEDIUM: 1.5, LOW: 0.5}
    penalty = sum(weights[issue_severity(i)] for r in results for i in r.issues)
    max_penalty = len(results) * 12
    return max(0, min(100, round(100 - (penalty / max_penalty) * 100))) if max_penalty else 100


def issue_breakdown(results: List[PageResult]) -> Dict[str, int]:
    counter: Counter = Counter()
    for result in results:
        for issue in result.issues:
            label = issue.split(" (")[0]
            if label.startswith("Redirected to"):
                label = "Redirected"
            elif label.startswith("Canonicalised to"):
                label = "Canonicalised to another URL"
            elif "image(s) missing ALT" in label:
                label = "Images missing ALT text"
            counter[label] += 1
    return dict(counter.most_common())


# ======================================================================
# 6. The crawl engine
# ======================================================================

@dataclass
class CrawlConfig:
    start_url: str
    max_pages: int = 100
    max_depth: int = 10
    delay: float = 0.5
    workers: int = 5
    timeout: float = 15.0
    user_agent: str = USER_AGENT
    respect_robots: bool = True
    include_subdomains: bool = False
    exclude_patterns: List[str] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)


class Crawler:
    """Breadth-first crawl of one site, run across a small thread pool."""

    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.start_url = normalize_url(config.start_url)
        if not self.start_url:
            raise ValueError(f"Invalid start URL: {config.start_url!r}")

        self.fetcher = Fetcher(config.user_agent, timeout=config.timeout)
        self.robots = RobotsHandler(config.user_agent, config.timeout, config.respect_robots)
        delay = config.delay
        robots_delay = self.robots.crawl_delay(self.start_url)
        if robots_delay:
            delay = max(delay, robots_delay)
        self.limiter = RateLimiter(delay)
        self.visited: Set[str] = set()
        self.results: List[PageResult] = []

    def _should_queue(self, url: str) -> bool:
        if url in self.visited:
            return False
        if not is_same_site(url, self.start_url, self.config.include_subdomains):
            return False
        if looks_like_file(url):
            return False
        return not any(p and p in url for p in self.config.exclude_patterns)

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
            result.seo = parse_page(fetched.html, fetched.final_url or url,
                                    self.start_url, self.config.include_subdomains)
        return result

    def crawl(self, on_progress=None) -> List[PageResult]:
        queue: deque = deque([(self.start_url, 0)])
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
                            break
                        if self._should_queue(link):
                            self.visited.add(link)
                            queue.append((link, result.depth + 1))

        self.fetcher.close()
        return analyze(self.results, self.config.thresholds)

    @property
    def queued_but_not_crawled(self) -> int:
        return max(0, len(self.visited) - len(self.results))


# ======================================================================
# 7. Report tables
# ======================================================================

def results_to_dataframe(results: List[PageResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        seo = r.seo
        rows.append({
            "URL": r.url,
            "Final URL": r.final_url,
            "Status Code": r.status_code if r.status_code is not None else "",
            "Response Time (s)": r.response_time,
            "Depth": r.depth,
            "Indexability": r.indexability,
            "Indexability Reason": r.indexability_reason,
            "Title": seo.title,
            "Title Length": seo.title_length,
            "Duplicate Title": "Yes" if r.duplicate_title else "No",
            "Meta Description": seo.meta_description,
            "Meta Length": seo.meta_description_length,
            "Duplicate Meta": "Yes" if r.duplicate_meta_description else "No",
            "H1": seo.h1,
            "H1 Count": seo.h1_count,
            "H2 Count": len(seo.h2_list),
            "Canonical": seo.canonical,
            "Canonical Status": r.canonical_status,
            "Meta Robots": seo.meta_robots,
            "Lang": seo.lang,
            "Hreflang Tags": seo.hreflang_count,
            "Schema Types": ", ".join(seo.schema_types),
            "Internal Links": len(seo.internal_links),
            "External Links": len(seo.external_links),
            "Images": seo.images_total,
            "Images Missing ALT": seo.images_missing_alt,
            "Word Count": seo.word_count,
            "Issue Count": r.issue_count,
            "Issues": truncate(" | ".join(r.issues), 500),
        })
    return pd.DataFrame(rows)


def issues_to_dataframe(results: List[PageResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        for issue in result.issues:
            rows.append({
                "URL": result.url,
                "Severity": issue_severity(issue),
                "Issue": issue,
                "Status Code": result.status_code or "",
                "Indexability": result.indexability,
            })
    if not rows:
        return pd.DataFrame(columns=["URL", "Severity", "Issue", "Status Code", "Indexability"])
    rows.sort(key=lambda row: (SEVERITY_ORDER[row["Severity"]], row["URL"]))
    return pd.DataFrame(rows)


def summary_to_dataframe(results: List[PageResult], start_url: str) -> pd.DataFrame:
    rows = [
        {"Metric": "Website", "Value": start_url},
        {"Metric": "Crawl date", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"Metric": "SEO health score (0-100)", "Value": health_score(results)},
    ]
    rows += [{"Metric": k, "Value": v} for k, v in build_summary(results).items()]
    return pd.DataFrame(rows)


def breakdown_to_dataframe(results: List[PageResult]) -> pd.DataFrame:
    total = len(results) or 1
    return pd.DataFrame([
        {"Issue Type": name, "Pages Affected": count,
         "% of Crawled Pages": round(count / total * 100, 1)}
        for name, count in issue_breakdown(results).items()
    ])


# ======================================================================
# 8. Streamlit interface
# ======================================================================

import os

HOSTED = os.getenv("HOSTED", "0") == "1"
MAX_PAGES_CAP = 50 if HOSTED else 500
MIN_DELAY = 0.3 if HOSTED else 0.0

st.set_page_config(page_title="Mini SEO Crawler", page_icon="🔎", layout="wide")
st.markdown("<style>.block-container{padding-top:2.5rem;max-width:1200px}</style>",
            unsafe_allow_html=True)

with st.sidebar:
    st.title("Crawl settings")
    max_pages = st.slider("Pages to crawl", 5, MAX_PAGES_CAP, min(25, MAX_PAGES_CAP), 5)
    delay = st.slider("Delay between requests (s)", MIN_DELAY, 3.0, max(0.5, MIN_DELAY), 0.1)
    workers = st.slider("Parallel workers", 1, 8, 4)
    max_depth = st.slider("Maximum link depth", 1, 10, 5)
    st.divider()
    exclude_raw = st.text_input("Skip URLs containing", placeholder="/tag/, /author/")
    include_subdomains = st.checkbox("Also crawl subdomains", value=False)
    respect_robots = st.checkbox("Respect robots.txt", value=True, disabled=HOSTED)
    st.divider()
    st.caption("Only crawl sites you own or have permission to audit.")

st.title("Mini SEO Crawler")
st.write("Crawl a site, extract every on-page SEO element, and download the audit as CSV or Excel.")

col_url, col_btn = st.columns([5, 1])
with col_url:
    url = st.text_input("Website URL", placeholder="https://example.com", label_visibility="collapsed")
with col_btn:
    start = st.button("Start crawl", type="primary", width="stretch")


def run_crawl(config: CrawlConfig):
    crawler = Crawler(config)
    progress = st.progress(0.0, text="Starting crawl…")
    log_box = st.empty()
    log_lines: List[str] = []

    def on_progress(done, total, result):
        code = result.error or result.status_code or "ERR"
        log_lines.append(f"[{done:>3}/{total}]  {code:<6} {result.response_time:>5.2f}s  {result.url}")
        progress.progress(min(done / total, 1.0), text=f"Crawled {done} of {total} pages")
        log_box.code("\n".join(log_lines[-12:]), language="text")

    started = time.perf_counter()
    results = crawler.crawl(on_progress=on_progress)
    elapsed = time.perf_counter() - started
    progress.progress(1.0, text=f"Done — {len(results)} pages in {elapsed:.1f}s")
    log_box.empty()
    return crawler, results


if start:
    if not url.strip():
        st.warning("Enter a website URL to crawl.")
    else:
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            target = "https://" + target
        config = CrawlConfig(
            start_url=target,
            max_pages=max_pages,
            max_depth=max_depth,
            delay=delay,
            workers=workers,
            respect_robots=True if HOSTED else respect_robots,
            include_subdomains=include_subdomains,
            exclude_patterns=[p.strip() for p in exclude_raw.split(",") if p.strip()],
        )
        try:
            crawler, results = run_crawl(config)
            st.session_state["results"] = results
            st.session_state["start_url"] = crawler.start_url
            st.session_state["not_crawled"] = crawler.queued_but_not_crawled
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Crawl failed: {exc.__class__.__name__} — {exc}")

results = st.session_state.get("results")

if results:
    start_url = st.session_state["start_url"]
    summary = build_summary(results)

    st.subheader("Results")
    row = st.columns(5)
    row[0].metric("SEO health score", f"{health_score(results)}/100")
    row[1].metric("Pages crawled", summary["Pages crawled"])
    row[2].metric("Indexable", summary["Indexable pages"])
    row[3].metric("Errors (4xx/5xx)", summary["4xx Client error"] + summary["5xx Server error"])
    row[4].metric("Issues found", summary["Total issues found"])

    if st.session_state.get("not_crawled"):
        st.info(f"{st.session_state['not_crawled']} more internal URLs were found but not crawled — "
                "raise the page limit to include them.")

    crawl_df = results_to_dataframe(results)
    issues_df = issues_to_dataframe(results)
    tab_pages, tab_issues, tab_breakdown, tab_summary = st.tabs(
        ["Crawl data", "Issues", "Issue breakdown", "Summary"])

    with tab_pages:
        only_problems = st.checkbox("Show only pages with issues", value=False)
        view = crawl_df[crawl_df["Issue Count"] > 0] if only_problems else crawl_df
        st.dataframe(view, width="stretch", hide_index=True, height=430)

    with tab_issues:
        if issues_df.empty:
            st.success("No issues found.")
        else:
            picked = st.multiselect("Severity", [CRITICAL, HIGH, MEDIUM, LOW],
                                    default=[CRITICAL, HIGH, MEDIUM])
            filtered = issues_df[issues_df["Severity"].isin(picked)] if picked else issues_df
            st.dataframe(filtered, width="stretch", hide_index=True, height=430)

    with tab_breakdown:
        breakdown_df = breakdown_to_dataframe(results)
        if breakdown_df.empty:
            st.success("Nothing to report.")
        else:
            st.bar_chart(breakdown_df.set_index("Issue Type")["Pages Affected"].head(12),
                         horizontal=True, height=380)
            st.dataframe(breakdown_df, width="stretch", hide_index=True)

    with tab_summary:
        summary_view = summary_to_dataframe(results, start_url)
        summary_view["Value"] = summary_view["Value"].astype(str)
        st.dataframe(summary_view, width="stretch", hide_index=True, height=430)

    st.subheader("Download the report")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_to_dataframe(results, start_url).to_excel(writer, sheet_name="Summary", index=False)
        crawl_df.to_excel(writer, sheet_name="Crawl Data", index=False)
        issues_df.to_excel(writer, sheet_name="Issues", index=False)
        breakdown_to_dataframe(results).to_excel(writer, sheet_name="Issue Breakdown", index=False)

    d1, d2, d3 = st.columns(3)
    d1.download_button("Crawl data (CSV)", crawl_df.to_csv(index=False).encode("utf-8-sig"),
                       "seo_crawl_report.csv", "text/csv", width="stretch")
    d2.download_button("Issues (CSV)", issues_df.to_csv(index=False).encode("utf-8-sig"),
                       "seo_crawl_issues.csv", "text/csv", width="stretch")
    d3.download_button("Full report (Excel)", buffer.getvalue(), "seo_crawl_report.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")

elif not start:
    st.info("Enter a URL above to run your first crawl.")
    with st.expander("What this checks on every page"):
        st.markdown(
            """
            **Response** — status code, final URL, redirect chain, response time, crawl depth
            **Indexability** — noindex, X-Robots-Tag, canonical conflicts, robots.txt blocks
            **Metadata** — title and meta description text, length and duplicates
            **Headings** — H1 text, H1 count, H2 count
            **Links** — internal, external and nofollow counts
            **Images** — total images and images missing ALT text
            **Content** — visible word count, thin-content flag
            **Extras** — html lang, viewport, hreflang tags, JSON-LD schema types
            """
        )
