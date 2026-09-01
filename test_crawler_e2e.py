"""End-to-end test: serve the bundled demo site and crawl it for real."""

import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from seo_crawler.analyzer import INDEXABLE
from seo_crawler.config import CrawlConfig
from seo_crawler.crawler import Crawler
from seo_crawler.report import generate_reports, results_to_dataframe

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_site")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence the server
        pass


@pytest.fixture(scope="module")
def demo_server():
    handler = functools.partial(QuietHandler, directory=DEMO_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def results(demo_server):
    config = CrawlConfig(
        start_url=demo_server, max_pages=20, delay=0, workers=4, respect_robots=True
    )
    return Crawler(config).crawl()


def by_path(results, suffix):
    return next(r for r in results if r.url.endswith(suffix))


class TestCrawlCoverage:
    def test_finds_all_demo_pages(self, results):
        paths = {r.url.rsplit("8", 1)[-1].split("/", 1)[-1] for r in results}
        assert len(results) == 9, paths

    def test_external_links_not_crawled(self, results):
        assert all("google.com" not in r.url for r in results)

    def test_no_duplicate_urls(self, results):
        urls = [r.url for r in results]
        assert len(urls) == len(set(urls))

    def test_broken_link_detected(self, results):
        assert by_path(results, "/missing.html").status_code == 404


class TestExtraction:
    def test_homepage_parsed(self, results):
        home = by_path(results, "/index.html")
        assert home.status_code == 200
        assert home.indexability == INDEXABLE
        assert home.seo.h1_count == 1
        assert home.seo.images_missing_alt == 1
        assert home.seo.internal_links

    def test_multiple_h1_page(self, results):
        about = by_path(results, "/about.html")
        assert about.seo.h1_count == 2
        assert any("Multiple H1" in i for i in about.issues)

    def test_noindex_page(self, results):
        old = by_path(results, "/old-page.html")
        assert "noindex" in old.seo.meta_robots
        assert "Noindex directive" in old.issues

    def test_canonicalised_page(self, results):
        thin = by_path(results, "/thin.html")
        assert thin.canonical_status == "Points to another URL"

    def test_duplicate_titles_found(self, results):
        assert by_path(results, "/thin.html").duplicate_title
        assert by_path(results, "/services.html").duplicate_title


class TestReports:
    def test_dataframe_shape(self, results):
        frame = results_to_dataframe(results)
        assert len(frame) == len(results)
        assert "Indexability" in frame.columns

    def test_report_files_written(self, results, demo_server, tmp_path):
        files = generate_reports(
            results, start_url=demo_server, output_dir=str(tmp_path), fmt="both"
        )
        assert len(files) == 3
        for path in files:
            assert os.path.exists(path) and os.path.getsize(path) > 0
