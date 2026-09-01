# Resume & Interview Notes

Not part of the codebase — this is your cheat sheet for putting the project on a CV,
portfolio or GitHub profile.

---

## 1. Resume bullets (pick 3–4)

**Mini SEO Crawler — Python | *Personal Project*** · [github.com/your-username/mini-seo-crawler](https://github.com/your-username/mini-seo-crawler)

- Built a multi-threaded technical SEO crawler in Python (`requests`, `BeautifulSoup`,
  `pandas`) that audits up to 500 pages per run and exports a formatted Excel report with
  a 0–100 site health score.
- Implemented breadth-first internal link discovery with URL normalisation (tracking
  parameter stripping, fragment removal, query sorting), cutting duplicate crawl requests.
- Automated detection of 20+ technical SEO issues — duplicate titles and meta
  descriptions, missing/multiple H1s, canonical conflicts, noindex directives, broken
  links, thin content and missing image ALT text — each scored by severity.
- Designed a layered architecture (fetcher / parser / analyzer / reporter) covered by 88
  unit and end-to-end tests, including a full crawl against a local test server.
- Replaced a manual audit step that previously took ~2 hours per client site with a
  single command producing a client-ready Excel deliverable.

> Swap the last bullet for a real number once you run it on a client site — for example
> "used to audit a 400-page ecommerce site, surfacing 60+ pages with duplicate metadata."

---

## 2. One-line portfolio description

> A Python crawler that audits a website's technical SEO — indexability, metadata,
> headings, canonicals, links, images and content depth — and exports a severity-scored
> CSV/Excel report.

---

## 3. Skills this project demonstrates

| Area | What to point to |
|---|---|
| Python | dataclasses, type hints, context managers, `ThreadPoolExecutor`, `argparse` |
| Web scraping | `requests` sessions, retry/backoff strategy, streaming response limits, BeautifulSoup parsing |
| Concurrency | thread pool with a shared, lock-based rate limiter |
| Data | pandas DataFrames, multi-sheet Excel via openpyxl with formatting |
| Testing | pytest fixtures, parametrised tests, a real HTTP server in an E2E test |
| SEO domain | indexability rules, canonicalisation, robots directives, duplicate content, crawl budget |
| Engineering practice | separation of concerns, docstrings, MIT license, README, packaging via `pyproject.toml` |

---

## 4. Likely interview questions

**"How do you avoid crawling the same page twice?"**
Every URL is normalised before it enters the queue — scheme and host lowercased, fragment
dropped, default port removed, tracking parameters stripped, remaining query parameters
sorted. The normalised form goes into a `visited` set, which is checked before queueing,
not before fetching, so a URL linked from 50 pages is still only fetched once.

**"Why breadth-first and not depth-first?"**
BFS reaches the most important pages first. Sites put their money pages one or two clicks
from the homepage, so if the crawl is capped at 100 pages, BFS spends that budget on
pages that matter instead of tunnelling into one blog archive.

**"How do you decide a page is not indexable?"**
A priority chain: robots.txt block → request error → 4xx/5xx → redirect → non-HTML →
noindex (meta or `X-Robots-Tag`) → canonical pointing elsewhere → otherwise indexable.
The first match wins and the reason is stored, so the report says *why*, not just *what*.

**"How is it polite to the sites it crawls?"**
Named User-Agent, robots.txt respected including `Crawl-delay`, a shared rate limiter so
all threads share one delay budget rather than each having its own, capped response size,
per-request timeouts, and a hard page limit.

**"What would you build next?"**
JavaScript rendering with Playwright, mapping which page links to each 404, and comparing
the crawl against the XML sitemap to find orphan pages.

---

## 5. Before pushing to GitHub

- [ ] Replace `your-username` in `README.md` and `RESUME_NOTES.md`
- [ ] Put your name in `LICENSE` and `pyproject.toml`
- [ ] Run `pytest` once and confirm everything passes
- [ ] Add a screenshot of the console summary and one of the Excel report to the README
- [ ] Pin the repo on your GitHub profile
