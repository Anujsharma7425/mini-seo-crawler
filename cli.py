"""Command line interface for the Mini SEO Crawler."""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

from .analyzer import PageResult, build_summary, health_score, issue_breakdown, top_issue_pages
from .config import DEFAULT_USER_AGENT, CrawlConfig, Thresholds
from .crawler import Crawler
from .report import generate_reports

LINE = "=" * 72


# ----------------------------------------------------------------------
# Console helpers
# ----------------------------------------------------------------------

def _supports_colour() -> bool:
    return sys.stdout.isatty()


class C:
    """Minimal ANSI colour helper (no external dependency)."""

    _on = _supports_colour()
    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    RED = "\033[31m" if _on else ""
    CYAN = "\033[36m" if _on else ""

    @classmethod
    def wrap(cls, text: str, colour: str) -> str:
        return f"{colour}{text}{cls.RESET}"


def _status_colour(code: Optional[int], error: str) -> str:
    if error or code is None:
        return C.RED
    if code >= 400:
        return C.RED
    if code >= 300:
        return C.YELLOW
    return C.GREEN


def print_progress(done: int, total: int, result: PageResult) -> None:
    code = result.error or (result.status_code if result.status_code is not None else "ERR")
    colour = _status_colour(result.status_code, result.error)
    url = result.url if len(result.url) <= 68 else result.url[:65] + "..."
    print(
        f"  [{done:>4}/{total}] {C.wrap(str(code), colour):<6} "
        f"{result.response_time:>5.2f}s  {url}"
    )


def print_summary(results: List[PageResult], start_url: str, elapsed: float) -> None:
    summary = build_summary(results)
    score = health_score(results)
    score_colour = C.GREEN if score >= 80 else C.YELLOW if score >= 60 else C.RED

    print(f"\n{LINE}\n{C.BOLD}CRAWL SUMMARY{C.RESET}  \u2014  {start_url}\n{LINE}")
    print(f"  SEO health score : {C.wrap(f'{score}/100', score_colour)}")
    print(f"  Time taken       : {elapsed:.1f}s")

    print(f"\n{C.BOLD}Response codes{C.RESET}")
    for key in ("Pages crawled", "2xx Success", "3xx Redirect", "4xx Client error",
                "5xx Server error", "Failed / no response", "Average response time (s)"):
        if key in summary:
            print(f"  {key:<32} {summary[key]}")

    print(f"\n{C.BOLD}Indexability{C.RESET}")
    for key in ("Indexable pages", "Non-indexable pages", "Noindex pages",
                "Canonicalised to another URL", "Missing canonical"):
        print(f"  {key:<32} {summary.get(key, 0)}")

    print(f"\n{C.BOLD}On-page SEO{C.RESET}")
    for key in ("Missing titles", "Duplicate titles", "Titles too long",
                "Missing meta descriptions", "Duplicate meta descriptions",
                "Missing H1", "Multiple H1", "Thin pages (<300 words)",
                "Images missing ALT (total)", "Pages with structured data"):
        print(f"  {key:<32} {summary.get(key, 0)}")

    breakdown = issue_breakdown(results)
    if breakdown:
        print(f"\n{C.BOLD}Top issue types{C.RESET}")
        for name, count in list(breakdown.items())[:10]:
            print(f"  {name:<40} {count} page(s)")

    worst = top_issue_pages(results, limit=5)
    if worst:
        print(f"\n{C.BOLD}Pages needing attention first{C.RESET}")
        for result in worst:
            print(f"  {result.issue_count:>2} issues  {result.url}")
            for issue in result.issues[:4]:
                print(f"           - {issue}")
    print(LINE)


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-crawler",
        description="Mini SEO Crawler v1 - crawl a website and export a technical SEO report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m seo_crawler https://example.com --max-pages 100\n"
            "  python -m seo_crawler https://example.com --exclude /tag/ /author/ --format xlsx\n"
            "  python -m seo_crawler   (interactive mode)\n"
        ),
    )
    parser.add_argument("url", nargs="?", help="Website URL to crawl")
    parser.add_argument("-m", "--max-pages", type=int, default=100, help="Maximum pages to crawl (default: 100)")
    parser.add_argument("-d", "--delay", type=float, default=0.5, help="Delay between requests in seconds (default: 0.5)")
    parser.add_argument("-w", "--workers", type=int, default=5, help="Parallel workers (default: 5)")
    parser.add_argument("--max-depth", type=int, default=10, help="Maximum link depth from the homepage (default: 10)")
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds (default: 15)")
    parser.add_argument("--include", nargs="*", default=[], metavar="PATTERN", help="Only crawl URLs containing these patterns")
    parser.add_argument("--exclude", nargs="*", default=[], metavar="PATTERN", help="Skip URLs containing these patterns")
    parser.add_argument("--include-subdomains", action="store_true", help="Also crawl subdomains of the start domain")
    parser.add_argument("--ignore-robots", action="store_true", help="Do not read robots.txt (use only on sites you own)")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Custom User-Agent string")
    parser.add_argument("-o", "--output-dir", default="output", help="Where to save reports (default: output/)")
    parser.add_argument("-f", "--format", choices=["csv", "xlsx", "both"], default="both", help="Report format (default: both)")
    parser.add_argument("--prefix", default="", help="Custom file name prefix for the reports")
    parser.add_argument("-q", "--quiet", action="store_true", help="Hide per-URL progress output")
    # thresholds
    parser.add_argument("--title-max", type=int, default=60, help="Max title length before flagging (default: 60)")
    parser.add_argument("--meta-max", type=int, default=160, help="Max meta description length (default: 160)")
    parser.add_argument("--min-words", type=int, default=300, help="Word count below which a page is thin (default: 300)")
    return parser


def prompt_for_input() -> tuple:
    """Interactive fallback when no URL is passed on the command line."""
    print(f"{LINE}\n{C.BOLD}Mini SEO Crawler v1{C.RESET}\n{LINE}")
    url = input("Website URL            : ").strip()
    raw_pages = input("Maximum pages [100]    : ").strip()
    max_pages = int(raw_pages) if raw_pages.isdigit() else 100
    return url, max_pages


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    url, max_pages = args.url, args.max_pages
    if not url:
        try:
            url, max_pages = prompt_for_input()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 1
    if not url:
        print("No URL provided.")
        return 1
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    config = CrawlConfig(
        start_url=url,
        max_pages=max_pages,
        max_depth=args.max_depth,
        delay=args.delay,
        workers=args.workers,
        timeout=args.timeout,
        user_agent=args.user_agent,
        respect_robots=not args.ignore_robots,
        include_subdomains=args.include_subdomains,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        thresholds=Thresholds(
            title_max=args.title_max,
            meta_desc_max=args.meta_max,
            min_word_count=args.min_words,
        ),
    )

    try:
        crawler = Crawler(config)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"\n{LINE}")
    print(f"{C.BOLD}Crawling{C.RESET} {crawler.start_url}  (max {config.max_pages} pages, "
          f"{config.workers} workers, {config.delay}s delay)")
    print(LINE)

    started = time.perf_counter()
    try:
        results = crawler.crawl(on_progress=None if args.quiet else print_progress)
    except KeyboardInterrupt:
        print("\nCrawl interrupted - writing a report for the pages collected so far...")
        from .analyzer import analyze

        results = analyze(crawler.results, config.thresholds)
    elapsed = time.perf_counter() - started

    if not results:
        print("No pages were crawled. Check the URL and your connection.")
        return 1

    print_summary(results, crawler.start_url, elapsed)

    files = generate_reports(
        results,
        start_url=crawler.start_url,
        output_dir=args.output_dir,
        fmt=args.format,
        prefix=args.prefix,
    )
    print(f"\n{C.BOLD}Reports saved{C.RESET}")
    for path in files:
        print(f"  {C.wrap(path, C.CYAN)}")
    if crawler.queued_but_not_crawled:
        print(f"\n  Note: {crawler.queued_but_not_crawled} more internal URL(s) were discovered "
              f"but not crawled (page limit reached).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
