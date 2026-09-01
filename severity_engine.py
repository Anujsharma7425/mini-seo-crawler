"""Severity scoring for technical SEO issues."""
from __future__ import annotations

SEVERITY_ORDER = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "Info": 0,
}


def score_issue(issue_code: str, context: dict | None = None) -> str:
    """Map an issue code to a practical default severity."""
    context = context or {}

    rules = {
        "HTTP_4XX": "Critical",
        "HTTP_5XX": "Critical",
        "REDIRECT_LOOP": "Critical",
        "NOINDEX": "High",
        "ROBOTS_BLOCKED": "High",
        "MISSING_TITLE": "High",
        "DUPLICATE_TITLE": "High",
        "MISSING_H1": "Medium",
        "MULTIPLE_H1": "Medium",
        "MISSING_CANONICAL": "Medium",
        "DUPLICATE_META": "Medium",
        "REDIRECT_CHAIN": "Medium",
        "INVALID_HREFLANG": "Medium",
        "MISSING_SCHEMA": "Low",
        "IMAGE_MISSING_ALT": "Low",
        "LOW_WORD_COUNT": "Low",
    }

    severity = rules.get(issue_code, "Info")

    # Example context-sensitive adjustment.
    if issue_code == "NOINDEX" and context.get("is_important_landing_page"):
        severity = "Critical"

    return severity


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, 0)
