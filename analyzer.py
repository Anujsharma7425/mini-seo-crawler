"""Turn raw crawl data into SEO verdicts: indexability, issues and a summary."""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import Thresholds
from .parser import PageSEO
from .utils import truncate

# Issue severities, used to sort the issue sheet.
CRITICAL = "Critical"
HIGH = "High"
MEDIUM = "Medium"
LOW = "Low"

SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}

# Indexability states
INDEXABLE = "Indexable"
NOINDEX = "Non-Indexable (noindex)"
REDIRECT = "Non-Indexable (redirect)"
CANONICALISED = "Non-Indexable (canonicalised)"
BLOCKED = "Non-Indexable (blocked by robots.txt)"
ERROR = "Non-Indexable (error)"
NON_HTML = "Non-Indexable (not HTML)"


@dataclass
class PageResult:
    """One row of the crawl report."""

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

    # ---- convenience accessors used by the report layer ----------------
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
    return directive in (result.seo.meta_robots or "").lower() or directive in (
        result.x_robots_tag or ""
    ).lower()


def set_indexability(result: PageResult) -> None:
    """Decide whether Google could index this URL, and record why not."""
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


def detect_issues(result: PageResult, thresholds: Thresholds) -> List[str]:
    """Return the list of SEO problems found on a single page."""
    issues: List[str] = []
    seo = result.seo

    # --- response level --------------------------------------------------
    if result.error:
        issues.append(f"Request failed ({result.error})")
        return issues
    if result.status_code and result.status_code >= 500:
        issues.append(f"Server error ({result.status_code})")
        return issues
    if result.status_code and 400 <= result.status_code < 500:
        issues.append(f"Broken URL ({result.status_code})")
        return issues
    if result.redirect_chain:
        issues.append(f"Redirected to {result.final_url}")
        if len(result.redirect_chain) > 1:
            issues.append(f"Redirect chain ({len(result.redirect_chain)} hops)")
    if result.blocked_by_robots:
        issues.append("Blocked by robots.txt")
        return issues
    if result.content_type and "html" not in result.content_type.lower():
        return issues
    if result.response_time > thresholds.slow_response:
        issues.append(f"Slow response ({result.response_time:.2f}s)")

    # --- indexation ------------------------------------------------------
    if _has_directive(result, "noindex"):
        issues.append("Noindex directive")
    if _has_directive(result, "nofollow"):
        issues.append("Page-level nofollow directive")

    # --- title -----------------------------------------------------------
    if not seo.title:
        issues.append("Missing title")
    else:
        if seo.title_length < thresholds.title_min:
            issues.append(f"Short title ({seo.title_length} chars)")
        elif seo.title_length > thresholds.title_max:
            issues.append(f"Long title ({seo.title_length} chars)")
        if result.duplicate_title:
            issues.append("Duplicate title")

    # --- meta description ------------------------------------------------
    if not seo.meta_description:
        issues.append("Missing meta description")
    else:
        if seo.meta_description_length < thresholds.meta_desc_min:
            issues.append(f"Short meta description ({seo.meta_description_length} chars)")
        elif seo.meta_description_length > thresholds.meta_desc_max:
            issues.append(f"Long meta description ({seo.meta_description_length} chars)")
        if result.duplicate_meta_description:
            issues.append("Duplicate meta description")

    # --- headings --------------------------------------------------------
    if seo.h1_count == 0:
        issues.append("Missing H1")
    elif seo.h1_count > thresholds.h1_max:
        issues.append(f"Multiple H1 tags ({seo.h1_count})")
    if result.duplicate_h1:
        issues.append("Duplicate H1")
    if seo.title and seo.h1 and seo.title.lower() == seo.h1.lower():
        issues.append("Title identical to H1")

    # --- canonical -------------------------------------------------------
    if result.canonical_status == "Missing":
        issues.append("Missing canonical")
    elif result.canonical_status == "Points to another URL":
        issues.append(f"Canonicalised to {seo.canonical}")

    # --- content ---------------------------------------------------------
    if seo.word_count < thresholds.min_word_count:
        issues.append(f"Low word count ({seo.word_count} words)")

    # --- images ----------------------------------------------------------
    if seo.images_missing_alt:
        issues.append(f"{seo.images_missing_alt} image(s) missing ALT text")

    # --- extras ----------------------------------------------------------
    if not seo.has_viewport:
        issues.append("Missing viewport meta tag (mobile)")
    if not seo.lang:
        issues.append("Missing html lang attribute")
    if not seo.schema_types:
        issues.append("No structured data (JSON-LD) found")

    return issues


def _mark_duplicates(results: List[PageResult]) -> None:
    """Flag duplicate titles / meta descriptions / H1s among indexable pages."""
    candidates = [r for r in results if r.status_code == 200 and not r.redirect_chain]

    def flag(attr_getter, setter) -> None:
        counts = Counter()
        for result in candidates:
            value = attr_getter(result)
            if value:
                counts[value.strip().lower()] += 1
        for result in candidates:
            value = attr_getter(result)
            if value and counts[value.strip().lower()] > 1:
                setter(result)

    flag(lambda r: r.seo.title, lambda r: setattr(r, "duplicate_title", True))
    flag(
        lambda r: r.seo.meta_description,
        lambda r: setattr(r, "duplicate_meta_description", True),
    )
    flag(lambda r: r.seo.h1, lambda r: setattr(r, "duplicate_h1", True))


def analyze(results: List[PageResult], thresholds: Thresholds) -> List[PageResult]:
    """Run every post-crawl check over the collected pages (in place)."""
    _mark_duplicates(results)
    for result in results:
        set_indexability(result)
        result.issues = detect_issues(result, thresholds)
    return results


def issue_severity(issue: str) -> str:
    """Map an issue string to a severity bucket."""
    lowered = issue.lower()
    if any(k in lowered for k in ("broken", "server error", "request failed", "blocked by robots")):
        return CRITICAL
    if any(k in lowered for k in ("noindex", "missing title", "missing h1", "canonicalised", "duplicate title")):
        return HIGH
    if any(
        k in lowered
        for k in (
            "missing meta description",
            "multiple h1",
            "missing canonical",
            "duplicate",
            "redirect",
            "alt text",
            "low word count",
            "slow response",
        )
    ):
        return MEDIUM
    return LOW


def build_summary(results: List[PageResult]) -> "OrderedDict[str, object]":
    """Aggregate counts for the console summary and the Summary sheet."""
    total = len(results)
    status_buckets = Counter()
    for result in results:
        code = result.status_code
        if result.error or code is None:
            status_buckets["Failed / no response"] += 1
        elif 200 <= code < 300:
            status_buckets["2xx Success"] += 1
        elif 300 <= code < 400:
            status_buckets["3xx Redirect"] += 1
        elif 400 <= code < 500:
            status_buckets["4xx Client error"] += 1
        else:
            status_buckets["5xx Server error"] += 1

    redirected = sum(1 for r in results if r.redirect_chain)
    html_pages = [r for r in results if r.status_code == 200 and not r.error]

    def count(predicate) -> int:
        return sum(1 for r in html_pages if predicate(r))

    summary: "OrderedDict[str, object]" = OrderedDict()
    summary["Pages crawled"] = total
    for label in ("2xx Success", "3xx Redirect", "4xx Client error", "5xx Server error", "Failed / no response"):
        summary[label] = status_buckets.get(label, 0)
    summary["Pages with redirects"] = redirected
    summary["Indexable pages"] = sum(1 for r in results if r.is_indexable)
    summary["Non-indexable pages"] = total - sum(1 for r in results if r.is_indexable)
    summary["Missing titles"] = count(lambda r: not r.seo.title)
    summary["Duplicate titles"] = count(lambda r: r.duplicate_title)
    summary["Titles too long"] = count(lambda r: r.seo.title_length > 60)
    summary["Missing meta descriptions"] = count(lambda r: not r.seo.meta_description)
    summary["Duplicate meta descriptions"] = count(lambda r: r.duplicate_meta_description)
    summary["Missing H1"] = count(lambda r: r.seo.h1_count == 0)
    summary["Multiple H1"] = count(lambda r: r.seo.h1_count > 1)
    summary["Missing canonical"] = count(lambda r: r.canonical_status == "Missing")
    summary["Canonicalised to another URL"] = count(
        lambda r: r.canonical_status == "Points to another URL"
    )
    summary["Noindex pages"] = count(lambda r: _has_directive(r, "noindex"))
    summary["Pages with missing image ALT"] = count(lambda r: r.seo.images_missing_alt > 0)
    summary["Images missing ALT (total)"] = sum(r.seo.images_missing_alt for r in html_pages)
    summary["Thin pages (<300 words)"] = count(lambda r: r.seo.word_count < 300)
    summary["Pages with structured data"] = count(lambda r: bool(r.seo.schema_types))
    summary["Total issues found"] = sum(r.issue_count for r in results)
    if results:
        summary["Average response time (s)"] = round(
            sum(r.response_time for r in results) / len(results), 3
        )
    return summary


def health_score(results: List[PageResult]) -> int:
    """A single 0-100 headline number, weighted by issue severity."""
    if not results:
        return 0
    weights = {CRITICAL: 5, HIGH: 3, MEDIUM: 1.5, LOW: 0.5}
    penalty = sum(
        weights[issue_severity(issue)] for result in results for issue in result.issues
    )
    max_penalty = len(results) * 12  # rough ceiling: a page with everything broken
    score = 100 - (penalty / max_penalty) * 100 if max_penalty else 100
    return max(0, min(100, round(score)))


def issue_breakdown(results: List[PageResult]) -> Dict[str, int]:
    """How many pages are affected by each issue type (labels normalised)."""
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


def top_issue_pages(results: List[PageResult], limit: int = 10) -> List[PageResult]:
    """Pages with the most problems, worst first."""
    ranked = sorted(results, key=lambda r: r.issue_count, reverse=True)
    return [r for r in ranked if r.issue_count][:limit]


def format_issue_rows(results: List[PageResult]) -> List[Dict[str, object]]:
    """Flatten pages into one row per issue for the Issues sheet."""
    rows: List[Dict[str, object]] = []
    for result in results:
        for issue in result.issues:
            rows.append(
                {
                    "URL": result.url,
                    "Severity": issue_severity(issue),
                    "Issue": issue,
                    "Status Code": result.status_code or "",
                    "Indexability": result.indexability,
                    "Title": truncate(result.seo.title, 120),
                }
            )
    rows.sort(key=lambda row: (SEVERITY_ORDER[row["Severity"]], row["URL"]))
    return rows
