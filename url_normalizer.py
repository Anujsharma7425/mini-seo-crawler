"""URL normalization helpers."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid"
}


def normalize_url(url: str, base_url: str | None = None, remove_tracking: bool = True) -> str:
    """Normalize a URL for crawl deduplication."""
    if base_url:
        url = urljoin(base_url, url)

    url, _ = urldefrag(url)
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query = parts.query
    if remove_tracking and query:
        params = [
            (k, v) for k, v in parse_qsl(query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        query = urlencode(params, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def same_domain(url: str, domain_url: str) -> bool:
    """Check whether two URLs share the same hostname."""
    return urlsplit(url).hostname == urlsplit(domain_url).hostname
