"""Tests for indexability logic, issue detection and the summary builder."""

from seo_crawler.analyzer import (
    CANONICALISED,
    ERROR,
    INDEXABLE,
    NOINDEX,
    REDIRECT,
    PageResult,
    analyze,
    build_summary,
    detect_issues,
    health_score,
    issue_severity,
    set_indexability,
)
from seo_crawler.config import Thresholds
from seo_crawler.parser import PageSEO

THRESHOLDS = Thresholds()


def make_page(url="https://example.com/", **overrides) -> PageResult:
    """A clean, fully optimised page that we then break on purpose."""
    seo = PageSEO(
        title="A perfectly reasonable page title for testing",
        title_length=46,
        meta_description=(
            "A meta description that is comfortably inside the recommended "
            "length window for Google search results pages."
        ),
        meta_robots="index, follow",
        canonical=url,
        h1_list=["Single H1"],
        lang="en",
        has_viewport=True,
        schema_types=["WebPage"],
        word_count=800,
    )
    seo.meta_description_length = len(seo.meta_description)
    result = PageResult(url=url, final_url=url, status_code=200, seo=seo)
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


class TestIndexability:
    def test_clean_page_is_indexable(self):
        page = make_page()
        set_indexability(page)
        assert page.indexability == INDEXABLE

    def test_noindex_meta(self):
        page = make_page()
        page.seo.meta_robots = "noindex, follow"
        set_indexability(page)
        assert page.indexability == NOINDEX

    def test_noindex_from_x_robots_header(self):
        page = make_page(x_robots_tag="noindex")
        set_indexability(page)
        assert page.indexability == NOINDEX

    def test_redirect(self):
        page = make_page(redirect_chain=[301])
        set_indexability(page)
        assert page.indexability == REDIRECT
        assert "301" in page.indexability_reason

    def test_404_is_error(self):
        page = make_page(status_code=404)
        set_indexability(page)
        assert page.indexability == ERROR

    def test_canonical_to_other_url(self):
        page = make_page()
        page.seo.canonical = "https://example.com/other"
        set_indexability(page)
        assert page.indexability == CANONICALISED

    def test_trailing_slash_still_self_referencing(self):
        page = make_page(url="https://example.com/about")
        page.seo.canonical = "https://example.com/about/"
        assert page.canonical_status == "Self-referencing"


class TestIssueDetection:
    def test_clean_page_has_no_issues(self):
        assert detect_issues(make_page(), THRESHOLDS) == []

    def test_missing_title(self):
        page = make_page()
        page.seo.title, page.seo.title_length = "", 0
        assert "Missing title" in detect_issues(page, THRESHOLDS)

    def test_long_title(self):
        page = make_page()
        page.seo.title = "x" * 90
        page.seo.title_length = 90
        assert any("Long title" in i for i in detect_issues(page, THRESHOLDS))

    def test_missing_meta_description(self):
        page = make_page()
        page.seo.meta_description, page.seo.meta_description_length = "", 0
        assert "Missing meta description" in detect_issues(page, THRESHOLDS)

    def test_missing_and_multiple_h1(self):
        page = make_page()
        page.seo.h1_list = []
        assert "Missing H1" in detect_issues(page, THRESHOLDS)
        page.seo.h1_list = ["a", "b"]
        assert any("Multiple H1" in i for i in detect_issues(page, THRESHOLDS))

    def test_missing_canonical(self):
        page = make_page()
        page.seo.canonical = ""
        assert "Missing canonical" in detect_issues(page, THRESHOLDS)

    def test_images_missing_alt(self):
        page = make_page()
        page.seo.images_total, page.seo.images_missing_alt = 5, 4
        assert any("4 image(s) missing ALT" in i for i in detect_issues(page, THRESHOLDS))

    def test_low_word_count(self):
        page = make_page()
        page.seo.word_count = 40
        assert any("Low word count" in i for i in detect_issues(page, THRESHOLDS))

    def test_broken_url_short_circuits(self):
        page = make_page(status_code=404)
        issues = detect_issues(page, THRESHOLDS)
        assert issues == ["Broken URL (404)"]

    def test_request_error_short_circuits(self):
        page = make_page(status_code=None, error="TIMEOUT")
        assert detect_issues(page, THRESHOLDS) == ["Request failed (TIMEOUT)"]

    def test_custom_threshold_is_respected(self):
        page = make_page()
        page.seo.word_count = 500
        relaxed = Thresholds(min_word_count=100)
        strict = Thresholds(min_word_count=1000)
        assert not any("Low word count" in i for i in detect_issues(page, relaxed))
        assert any("Low word count" in i for i in detect_issues(page, strict))


class TestDuplicatesAndSummary:
    def _pair(self):
        first = make_page("https://example.com/a")
        second = make_page("https://example.com/b")
        second.seo.title = first.seo.title
        second.seo.meta_description = first.seo.meta_description
        return [first, second]

    def test_duplicate_titles_flagged(self):
        pages = analyze(self._pair(), THRESHOLDS)
        assert all(p.duplicate_title for p in pages)
        assert all("Duplicate title" in p.issues for p in pages)

    def test_unique_titles_not_flagged(self):
        pages = self._pair()
        pages[1].seo.title = "A completely different and unique page title here"
        analyze(pages, THRESHOLDS)
        assert not any(p.duplicate_title for p in pages)

    def test_redirects_excluded_from_duplicate_check(self):
        pages = self._pair()
        pages[1].redirect_chain = [301]
        analyze(pages, THRESHOLDS)
        assert not pages[0].duplicate_title

    def test_summary_counts(self):
        pages = [make_page("https://example.com/a"), make_page("https://example.com/b", status_code=404)]
        analyze(pages, THRESHOLDS)
        summary = build_summary(pages)
        assert summary["Pages crawled"] == 2
        assert summary["2xx Success"] == 1
        assert summary["4xx Client error"] == 1
        assert summary["Indexable pages"] == 1

    def test_health_score_range(self):
        clean = analyze([make_page()], THRESHOLDS)
        assert health_score(clean) == 100
        broken = make_page(status_code=500)
        assert health_score(analyze([broken], THRESHOLDS)) < 100
        assert health_score([]) == 0

    def test_severity_mapping(self):
        assert issue_severity("Broken URL (404)") == "Critical"
        assert issue_severity("Missing title") == "High"
        assert issue_severity("Missing meta description") == "Medium"
        assert issue_severity("Missing html lang attribute") == "Low"
