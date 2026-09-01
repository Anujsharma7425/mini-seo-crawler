"""Centralized SEO rules for Mini SEO Crawler V2."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleResult:
    code: str
    severity: str
    message: str


def evaluate_page(page: dict) -> list[RuleResult]:
    """Evaluate a crawler row and return SEO issues."""
    issues = []

    status = page.get("status_code")
    if isinstance(status, int):
        if 500 <= status <= 599:
            issues.append(RuleResult("HTTP_5XX", "Critical", f"Server error: {status}"))
        elif 400 <= status <= 499:
            issues.append(RuleResult("HTTP_4XX", "Critical", f"Client error: {status}"))

    title = (page.get("title") or "").strip()
    if not title:
        issues.append(RuleResult("MISSING_TITLE", "High", "Title tag is missing."))
    elif len(title) > 60:
        issues.append(RuleResult("LONG_TITLE", "Low", "Title is longer than 60 characters."))

    meta = (page.get("meta_description") or "").strip()
    if not meta:
        issues.append(RuleResult(
            "MISSING_META_DESCRIPTION", "Medium", "Meta description is missing."
        ))

    h1_count = int(page.get("h1_count") or 0)
    if h1_count == 0:
        issues.append(RuleResult("MISSING_H1", "Medium", "No H1 was found."))
    elif h1_count > 1:
        issues.append(RuleResult(
            "MULTIPLE_H1", "Medium", f"{h1_count} H1 elements were found."
        ))

    canonical = (page.get("canonical") or "").strip()
    if not canonical:
        issues.append(RuleResult(
            "MISSING_CANONICAL", "Medium", "Canonical link is missing."
        ))

    robots = (page.get("meta_robots") or "").lower()
    if "noindex" in robots:
        issues.append(RuleResult("NOINDEX", "High", "Page contains a noindex directive."))

    missing_alt = int(page.get("images_missing_alt") or 0)
    if missing_alt:
        issues.append(RuleResult(
            "IMAGE_MISSING_ALT", "Low",
            f"{missing_alt} image(s) are missing ALT text."
        ))

    word_count = int(page.get("word_count") or 0)
    if 0 < word_count < 300:
        issues.append(RuleResult(
            "LOW_WORD_COUNT", "Low",
            f"Approximate visible word count is only {word_count}."
        ))

    return issues
