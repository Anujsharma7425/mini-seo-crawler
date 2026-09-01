"""Tests for on-page element extraction."""

from seo_crawler.parser import parse_page

FULL_PAGE = """
<!DOCTYPE html>
<html lang="en-GB">
<head>
  <title>  Best Ecommerce Fulfilment Services | Example  </title>
  <meta name="description" content="We ship your orders across Europe.">
  <meta name="robots" content="INDEX, FOLLOW">
  <meta name="viewport" content="width=device-width">
  <meta property="og:title" content="OG Title">
  <link rel="canonical" href="/about">
  <link rel="alternate" hreflang="nl" href="/nl/about">
  <link rel="alternate" hreflang="de" href="/de/about">
  <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Organization","name":"Example"}
  </script>
</head>
<body>
  <h1>Main heading</h1>
  <h2>Second</h2><h2>Another</h2>
  <h3>Third</h3>
  <p>Five visible words right here.</p>
  <script>var hidden = "this text must not be counted at all";</script>
  <style>.x{color:red}</style>
  <img src="a.jpg" alt="With alt">
  <img src="b.jpg" alt="">
  <img src="c.jpg">
  <a href="/services">Internal</a>
  <a href="https://example.com/contact">Also internal</a>
  <a href="https://facebook.com/example" rel="nofollow">External</a>
  <a href="mailto:hi@example.com">Mail</a>
  <a href="#top">Anchor</a>
</body>
</html>
"""

PAGE_URL = "https://example.com/about"
ROOT = "https://example.com/"


def parsed():
    return parse_page(FULL_PAGE, PAGE_URL, ROOT)


class TestTitleAndMeta:
    def test_title_is_trimmed(self):
        assert parsed().title == "Best Ecommerce Fulfilment Services | Example"

    def test_title_length(self):
        seo = parsed()
        assert seo.title_length == len(seo.title) == 44

    def test_meta_description(self):
        seo = parsed()
        assert seo.meta_description == "We ship your orders across Europe."
        assert seo.meta_description_length == 34

    def test_meta_robots_lowercased(self):
        assert parsed().meta_robots == "index, follow"

    def test_viewport_and_lang_and_og(self):
        seo = parsed()
        assert seo.has_viewport is True
        assert seo.lang == "en-GB"
        assert seo.og_title == "OG Title"


class TestHeadings:
    def test_h1(self):
        seo = parsed()
        assert seo.h1 == "Main heading"
        assert seo.h1_count == 1

    def test_h2_h3(self):
        seo = parsed()
        assert seo.h2_list == ["Second", "Another"]
        assert seo.h3_list == ["Third"]

    def test_multiple_h1_counted(self):
        seo = parse_page("<h1>One</h1><h1>Two</h1>", PAGE_URL, ROOT)
        assert seo.h1_count == 2


class TestCanonicalAndSchema:
    def test_canonical_is_absolute(self):
        assert parsed().canonical == "https://example.com/about"

    def test_hreflang_counted(self):
        assert parsed().hreflang_count == 2

    def test_schema_types(self):
        assert parsed().schema_types == ["Organization"]

    def test_invalid_json_ld_is_ignored(self):
        seo = parse_page(
            '<script type="application/ld+json">{not json}</script>', PAGE_URL, ROOT
        )
        assert seo.schema_types == []


class TestLinksAndImages:
    def test_internal_links(self):
        internal = parsed().internal_links
        assert internal == {"https://example.com/services", "https://example.com/contact"}

    def test_external_links(self):
        assert parsed().external_links == {"https://facebook.com/example"}

    def test_nofollow_counted(self):
        assert parsed().nofollow_links == 1

    def test_images(self):
        seo = parsed()
        assert seo.images_total == 3
        assert seo.images_missing_alt == 2  # empty alt and no alt


class TestWordCount:
    def test_visible_text_counted(self):
        # headings + paragraph + anchor text, nothing from <script>/<style>
        assert parsed().word_count == 16

    def test_script_and_style_are_excluded(self):
        html = (
            "<body><script>var a = 'one two three four five';</script>"
            "<style>.a{color:red}</style><p>Only these four words</p></body>"
        )
        assert parse_page(html, PAGE_URL, ROOT).word_count == 4

    def test_empty_html(self):
        seo = parse_page("", PAGE_URL, ROOT)
        assert seo.word_count == 0
        assert seo.title == ""
