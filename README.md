# Mini SEO Crawler v1

A lightweight technical SEO crawler written in pure Python. Give it a URL, it crawls the
site breadth-first, extracts every on-page SEO element, flags problems, and exports a
formatted CSV + Excel audit report with an SEO health score.

Built as a small, readable alternative to Screaming Frog for quick technical audits and
for automating repetitive crawl checks.

```
python run.py https://example.com --max-pages 100
```

---

## Features

**Crawling**
- Breadth-first internal link discovery starting from the homepage
- Multi-threaded fetching (`ThreadPoolExecutor`) with a shared, thread-safe rate limiter
- Same-domain only, with an optional `--include-subdomains` flag
- URL normalisation so `?utm_source=…`, `#fragments`, default ports and parameter order
  never create duplicate crawls
- `robots.txt` support, including `Crawl-delay`
- Include / exclude URL patterns, depth limit, page limit
- Automatic retries on 429/5xx, timeouts and connection errors handled per URL — one bad
  page never kills the crawl
- `Ctrl+C` writes a report for whatever was crawled so far

**Extracted per URL**

| Group | Data |
|---|---|
| Response | URL, final URL, status code, response time, content type, redirect chain, crawl depth |
| Title | text, length, duplicate flag |
| Meta description | text, length, duplicate flag |
| Headings | H1 text, H1 count, H2 count, H3s |
| Canonical | canonical URL + status (missing / self-referencing / points elsewhere) |
| Robots | meta robots, `X-Robots-Tag` header, noindex, nofollow |
| Links | internal count, external count, nofollow count |
| Images | total images, images missing ALT |
| Content | visible word count (scripts and styles stripped) |
| Extras | `html lang`, viewport, hreflang tag count, JSON-LD schema types |
| Verdict | indexability status + reason, issue list, issue count |

**Issue detection**

Missing / short / long / duplicate titles · missing / short / long / duplicate meta
descriptions · missing H1 · multiple H1 · duplicate H1 · title identical to H1 · missing
canonical · canonicalised to another URL · noindex · nofollow · broken URLs (4xx) · server
errors (5xx) · redirects and redirect chains · slow responses · thin content · images
missing ALT · missing viewport · missing `lang` · no structured data.

Every issue is scored `Critical / High / Medium / Low` and rolled into a **0–100 SEO
health score**.

**Reports**
- `seo_crawl_<domain>_<timestamp>.csv` — the full crawl table
- `..._issues.csv` — one row per issue, sorted by severity
- `..._.xlsx` — four formatted sheets: **Summary**, **Crawl Data**, **Issues**,
  **Issue Breakdown** (frozen headers, auto-filters, sized columns)
- A colour-coded console summary while it runs

---

## Web version

There is a Streamlit UI as well as the CLI:

```bash
pip install -r requirements-web.txt
streamlit run app.py
```

It runs the same crawler, streams progress live, and offers the CSV and Excel exports as
download buttons. See [DEPLOY.md](DEPLOY.md) for hosting it for free.

---

## Installation

```bash
git clone https://github.com/your-username/mini-seo-crawler.git
cd mini-seo-crawler
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.8+. Dependencies: `requests`, `beautifulsoup4`, `lxml`, `pandas`, `openpyxl`.

---

## Usage

Interactive (just run it and answer two questions):

```bash
python run.py
```

```
Website URL            : https://example.com
Maximum pages [100]    : 100
```

Command line:

```bash
# basic crawl
python run.py https://example.com --max-pages 200

# skip tag and author archives, Excel only
python run.py https://example.com --exclude /tag/ /author/ --format xlsx

# gentle crawl of a slow server
python run.py https://example.com --workers 2 --delay 2 --timeout 30

# only crawl the blog, 3 levels deep
python run.py https://example.com --include /blog/ --max-depth 3

# as a module
python -m seo_crawler https://example.com -m 50 -o reports/
```

### Options

| Flag | Default | Description |
|---|---|---|
| `-m, --max-pages` | 100 | Maximum pages to crawl |
| `-d, --delay` | 0.5 | Seconds between requests (raised automatically if robots.txt asks for more) |
| `-w, --workers` | 5 | Parallel request threads |
| `--max-depth` | 10 | Maximum link depth from the start URL |
| `--timeout` | 15 | Per-request timeout in seconds |
| `--include` | – | Only crawl URLs matching these patterns |
| `--exclude` | – | Skip URLs matching these patterns |
| `--include-subdomains` | off | Also crawl subdomains |
| `--ignore-robots` | off | Skip robots.txt (only on sites you own) |
| `--user-agent` | MiniSEOCrawler/1.0 | Custom User-Agent |
| `-o, --output-dir` | `output` | Report destination |
| `-f, --format` | both | `csv`, `xlsx` or `both` |
| `--title-max` / `--meta-max` / `--min-words` | 60 / 160 / 300 | Issue thresholds |
| `-q, --quiet` | off | Hide per-URL progress |

---

## Use it as a library

```python
from seo_crawler import CrawlConfig, Crawler, generate_reports

config = CrawlConfig(start_url="https://example.com", max_pages=50, delay=0.3)
results = Crawler(config).crawl()

for page in results:
    if not page.is_indexable:
        print(page.url, "->", page.indexability_reason)

generate_reports(results, start_url=config.start_url, output_dir="reports")
```

---

## Sample output

```
========================================================================
CRAWL SUMMARY  —  https://example.com
========================================================================
  SEO health score : 54/100
  Time taken       : 41.2s

Response codes
  Pages crawled                    100
  2xx Success                      87
  3xx Redirect                     5
  4xx Client error                 8

Indexability
  Indexable pages                  76
  Non-indexable pages              24
  Noindex pages                    4

On-page SEO
  Missing titles                   3
  Duplicate titles                 4
  Missing meta descriptions        12
  Missing H1                       2
  Multiple H1                      6
  Images missing ALT (total)       31

Pages needing attention first
   8 issues  https://example.com/contact
           - Long title (87 chars)
           - Missing H1
           - Missing canonical
```

Real generated reports from the bundled demo site live in [`examples/`](examples/).

---

## Try it offline

The repo ships with a small demo site containing deliberate SEO mistakes (duplicate
titles, a double H1, a noindex page, a broken link, a cross-canonical, missing ALT text):

```bash
cd demo_site && python -m http.server 8899 &
cd .. && python run.py http://127.0.0.1:8899/index.html --max-pages 20 --delay 0
```

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

88 tests covering URL normalisation, HTML extraction, indexability rules, issue
detection, duplicate detection and a full end-to-end crawl against a local test server.

---

## Project structure

```
mini-seo-crawler/
├── seo_crawler/
│   ├── config.py      # CrawlConfig + issue thresholds
│   ├── utils.py       # URL normalisation, same-site checks, rate limiter
│   ├── robots.py      # robots.txt fetching, caching, crawl-delay
│   ├── fetcher.py     # HTTP session, retries, timeouts, redirect tracking
│   ├── parser.py      # BeautifulSoup extraction of on-page elements
│   ├── analyzer.py    # indexability, issues, duplicates, health score
│   ├── crawler.py     # breadth-first crawl engine
│   ├── report.py      # CSV + formatted Excel output
│   └── cli.py         # argparse CLI, progress, console summary
├── tests/            # 88 pytest tests
├── demo_site/        # local site with deliberate SEO mistakes
├── examples/         # real generated reports
├── landing/          # static project page (Netlify / GitHub Pages)
├── app.py            # Streamlit web UI
└── run.py            # CLI entry point
```

Each layer is independent: the parser has no idea what HTTP is, the analyzer has no idea
what BeautifulSoup is, and the crawler just wires them together. That is what makes the
whole thing testable without hitting the network.

---

## Crawl politeness

The crawler identifies itself with a User-Agent, reads `robots.txt`, honours
`Crawl-delay`, applies its own delay between requests, limits response size to 3 MB, and
stops at the page limit. Please only crawl sites you own or have permission to audit.

---

## Roadmap (v2 / v3)

- JavaScript rendering via Playwright for SPA sites
- Broken internal link source mapping (which page links to each 404)
- XML sitemap parsing and sitemap-vs-crawl comparison
- Google Search Console + GA4 API enrichment
- Core Web Vitals via PageSpeed Insights API
- Hreflang cluster validation for multilingual sites
- AI-generated fix suggestions per issue
- Scheduled crawls with n8n and change alerts

---

## License

MIT — see [LICENSE](LICENSE).
