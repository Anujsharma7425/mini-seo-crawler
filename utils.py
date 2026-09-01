"""URL helpers and small shared utilities."""

from __future__ import annotations

import re
import threading
import time
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Query parameters that never change the page content, only analytics.
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "gbraid",
    "wbraid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "_ga",
    "yclid",
}

# File extensions we never want to fetch and parse as HTML.
NON_HTML_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".avif",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".zip", ".rar", ".gz", ".tar", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".webm", ".ogg", ".wav",
    ".css", ".js", ".json", ".xml", ".rss", ".txt",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".exe", ".dmg", ".apk",
}

DEFAULT_PORTS = {"http": "80", "https": "443"}

_WORD_RE = re.compile(r"[A-Za-z0-9\u00C0-\u024F\u0900-\u097F']+")

_INVALID_HOST_CHARS = re.compile(r"[\s<>\"'`\\|^{}\[\]()]")
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def is_valid_host(host: str) -> bool:
    """True when ``host`` looks like a real hostname, IP or localhost."""
    if not host or _INVALID_HOST_CHARS.search(host):
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if ":" in host or _IPV4_RE.fullmatch(host):  # IPv6 / IPv4
        return True
    return "." in host and not host.startswith(".") and not host.endswith(".")


def safe_filename(value: str) -> str:
    """Make a string safe to use inside a file name."""
    cleaned = _UNSAFE_FILENAME.sub("_", value).strip("._-")
    return cleaned or "report"


def normalize_url(url: str, base: Optional[str] = None) -> Optional[str]:
    """Return a canonical, comparable form of ``url``.

    Steps: resolve against ``base``, drop the fragment, lowercase the scheme
    and host, drop default ports, remove tracking parameters and sort the
    remaining query string so that ``?b=2&a=1`` and ``?a=1&b=2`` dedupe.
    Returns ``None`` for anything that is not a usable http(s) URL.
    """
    if not url:
        return None

    url = url.strip().replace("\n", "").replace("\t", "")
    if not url or url.startswith(("javascript:", "mailto:", "tel:", "#", "data:", "sms:")):
        return None

    if base:
        url = urljoin(base, url)

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if not is_valid_host(hostname):
        return None

    netloc = hostname
    if parts.port and str(parts.port) != DEFAULT_PORTS.get(scheme):
        netloc = f"{hostname}:{parts.port}"

    path = parts.path or "/"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs), doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def get_host(url: str) -> str:
    """Hostname of a URL, lowercased and without ``www.``."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(url: str, root_url: str, include_subdomains: bool = False) -> bool:
    """True when ``url`` belongs to the same site as ``root_url``."""
    host, root = get_host(url), get_host(root_url)
    if not host or not root:
        return False
    if host == root:
        return True
    return include_subdomains and host.endswith("." + root)


def looks_like_file(url: str) -> bool:
    """True when the URL path ends in an extension we should not parse."""
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    if dot == -1:
        return False
    return path[dot:] in NON_HTML_EXTENSIONS


def matches_any(url: str, patterns: Iterable[str]) -> bool:
    """True when the URL contains any of the given substrings/regexes."""
    for pattern in patterns:
        if pattern and (pattern in url or re.search(pattern, url)):
            return True
    return False


def count_words(text: str) -> int:
    """Approximate visible word count."""
    return len(_WORD_RE.findall(text or ""))


def truncate(value: Optional[str], limit: int = 300) -> str:
    """Trim long strings so the report stays readable."""
    if not value:
        return ""
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "\u2026"


class RateLimiter:
    """Thread-safe delay between requests, shared by all worker threads."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = max(0.0, delay)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            if sleep_for < 0:
                sleep_for = 0.0
            self._next_allowed = now + sleep_for + self.delay
        if sleep_for:
            time.sleep(sleep_for)
