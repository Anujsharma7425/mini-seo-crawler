"""Tests for URL normalisation and helpers."""

import pytest

from seo_crawler.utils import (
    count_words,
    get_host,
    is_same_site,
    looks_like_file,
    matches_any,
    normalize_url,
    safe_filename,
    truncate,
)


class TestNormalizeUrl:
    def test_strips_fragment_and_lowercases_host(self):
        assert normalize_url("HTTPS://Example.COM/About#team") == "https://example.com/About"

    def test_adds_root_path(self):
        assert normalize_url("https://example.com") == "https://example.com/"

    def test_removes_default_port(self):
        assert normalize_url("https://example.com:443/x") == "https://example.com/x"

    def test_keeps_custom_port(self):
        assert normalize_url("http://example.com:8080/x") == "http://example.com:8080/x"

    def test_drops_tracking_params_and_sorts_query(self):
        url = "https://example.com/p?utm_source=news&b=2&a=1&gclid=xyz"
        assert normalize_url(url) == "https://example.com/p?a=1&b=2"

    def test_resolves_relative_against_base(self):
        result = normalize_url("../services", base="https://example.com/blog/post/")
        assert result == "https://example.com/blog/services"

    @pytest.mark.parametrize(
        "value",
        ["", "  ", "#section", "javascript:void(0)", "mailto:a@b.com", "tel:+31000", "ftp://x.com/f"],
    )
    def test_rejects_non_crawlable(self, value):
        assert normalize_url(value) is None

    @pytest.mark.parametrize(
        "value",
        ["https://not a url", "https://nodot", "https://.example.com", "https://example.com."],
    )
    def test_rejects_invalid_hosts(self, value):
        assert normalize_url(value) is None

    @pytest.mark.parametrize(
        "value",
        ["http://localhost:8899/x", "http://127.0.0.1:8000/x", "https://sub.example.co.uk/x"],
    )
    def test_accepts_valid_hosts(self, value):
        assert normalize_url(value) is not None


class TestFilenames:
    def test_safe_filename_strips_unsafe_chars(self):
        assert safe_filename("not a url") == "not_a_url"
        assert safe_filename("example.com") == "example.com"

    def test_safe_filename_never_empty(self):
        assert safe_filename("///") == "report"


class TestSameSite:
    def test_www_and_root_are_same_site(self):
        assert is_same_site("https://www.example.com/a", "https://example.com/")

    def test_different_domain(self):
        assert not is_same_site("https://facebook.com/x", "https://example.com/")

    def test_subdomain_excluded_by_default(self):
        assert not is_same_site("https://blog.example.com/x", "https://example.com/")

    def test_subdomain_included_when_enabled(self):
        assert is_same_site("https://blog.example.com/x", "https://example.com/", True)

    def test_get_host_strips_www(self):
        assert get_host("https://www.Example.com/a") == "example.com"


class TestMisc:
    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/file.pdf", True),
        ("https://example.com/img/photo.JPG", True),
        ("https://example.com/about", False),
        ("https://example.com/blog/post-1.html", False),
    ])
    def test_looks_like_file(self, url, expected):
        assert looks_like_file(url) is expected

    def test_matches_any(self):
        assert matches_any("https://example.com/tag/seo", ["/tag/"])
        assert not matches_any("https://example.com/blog", ["/tag/", "/author/"])

    def test_count_words(self):
        assert count_words("Hello world, this is SEO!") == 5
        assert count_words("") == 0

    def test_truncate(self):
        assert truncate("a b  c") == "a b c"
        assert len(truncate("x" * 500, 100)) == 100
