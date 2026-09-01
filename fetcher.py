"""HTTP layer: one polite, retrying session shared by all workers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MAX_BYTES = 3 * 1024 * 1024  # never download more than 3 MB of HTML


@dataclass
class FetchResult:
    """Raw outcome of a single HTTP request."""

    url: str
    final_url: str = ""
    status_code: Optional[int] = None
    response_time: float = 0.0
    content_type: str = ""
    content_length: int = 0
    html: Optional[str] = None
    redirect_chain: List[int] = field(default_factory=list)
    redirect_target: str = ""
    x_robots_tag: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300

    @property
    def is_html(self) -> bool:
        return "html" in (self.content_type or "").lower()


class Fetcher:
    """Thin wrapper around ``requests.Session`` with sane crawler defaults."""

    def __init__(self, user_agent: str, timeout: float = 15.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self, url: str) -> FetchResult:
        """GET a URL and return a :class:`FetchResult`, never raising."""
        result = FetchResult(url=url, final_url=url)
        started = time.perf_counter()
        try:
            response = self.session.get(
                url, timeout=self.timeout, allow_redirects=True, stream=True
            )
            result.status_code = response.status_code
            result.final_url = response.url
            result.content_type = response.headers.get("Content-Type", "")
            result.x_robots_tag = response.headers.get("X-Robots-Tag", "")
            result.redirect_chain = [r.status_code for r in response.history]
            if response.history:
                result.redirect_target = response.url

            if result.is_html:
                content = response.raw.read(MAX_BYTES, decode_content=True) or b""
                result.content_length = len(content)
                encoding = response.encoding or response.apparent_encoding or "utf-8"
                result.html = content.decode(encoding, errors="replace")
            else:
                result.content_length = int(response.headers.get("Content-Length") or 0)
            response.close()
        except requests.exceptions.Timeout:
            result.error = "TIMEOUT"
        except requests.exceptions.TooManyRedirects:
            result.error = "TOO_MANY_REDIRECTS"
        except requests.exceptions.SSLError as exc:
            result.error = f"SSL_ERROR: {exc.__class__.__name__}"
        except requests.exceptions.ConnectionError:
            result.error = "CONNECTION_ERROR"
        except requests.RequestException as exc:
            result.error = f"REQUEST_ERROR: {exc.__class__.__name__}"
        except Exception as exc:  # pragma: no cover - defensive
            result.error = f"UNEXPECTED_ERROR: {exc.__class__.__name__}"
        finally:
            result.response_time = round(time.perf_counter() - started, 3)
        return result

    def close(self) -> None:
        self.session.close()
