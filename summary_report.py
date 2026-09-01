"""Simple crawl summary generator."""
from __future__ import annotations

from collections import Counter


def build_summary(rows: list[dict]) -> dict:
    """Build aggregate crawl statistics from crawler rows."""
    status = Counter()
    severity = Counter()
    issues = Counter()

    for row in rows:
        code = row.get("status_code")
        if code is not None:
            status[str(code)] += 1

        for issue in row.get("issues", []) or []:
            severity[issue.get("severity", "Info")] += 1
            issues[issue.get("code", "UNKNOWN")] += 1

    return {
        "pages_crawled": len(rows),
        "status_codes": dict(status),
        "severity_counts": dict(severity),
        "issue_counts": dict(issues),
    }
