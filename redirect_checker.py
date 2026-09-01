"""Redirect analysis utilities."""
from __future__ import annotations

import requests


def check_redirects(url: str, timeout: int = 15, max_redirects: int = 10) -> dict:
    """Inspect redirect chain and final response."""
    session = requests.Session()
    session.headers.update({"User-Agent": "MiniSEOCrawler/2.0"})

    chain = []
    current = url

    for _ in range(max_redirects + 1):
        try:
            response = session.get(
                current,
                timeout=timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            return {
                "url": url,
                "final_url": current,
                "status_code": None,
                "redirect_count": len(chain),
                "redirect_chain": chain,
                "error": str(exc),
                "is_redirect_loop": False,
            }

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            chain.append({
                "from": current,
                "status_code": response.status_code,
                "to": location,
            })
            if not location:
                break

            next_url = requests.compat.urljoin(current, location)
            if next_url in [item["from"] for item in chain]:
                return {
                    "url": url,
                    "final_url": next_url,
                    "status_code": response.status_code,
                    "redirect_count": len(chain),
                    "redirect_chain": chain,
                    "error": None,
                    "is_redirect_loop": True,
                }
            current = next_url
            continue

        return {
            "url": url,
            "final_url": current,
            "status_code": response.status_code,
            "redirect_count": len(chain),
            "redirect_chain": chain,
            "error": None,
            "is_redirect_loop": False,
        }

    return {
        "url": url,
        "final_url": current,
        "status_code": None,
        "redirect_count": len(chain),
        "redirect_chain": chain,
        "error": "Maximum redirects exceeded",
        "is_redirect_loop": True,
    }
