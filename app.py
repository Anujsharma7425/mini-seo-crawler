"""Streamlit web UI for the Mini SEO Crawler.

Run locally:      streamlit run app.py
Deploy:           Streamlit Community Cloud, Hugging Face Spaces, Render, Railway

Set HOSTED=1 in the environment on a public deployment to apply the safety caps
below (smaller page limit, enforced delay, robots.txt always respected).
"""

from __future__ import annotations

import io
import os
import time

import pandas as pd
import streamlit as st

from seo_crawler import CrawlConfig, Crawler, __version__
from seo_crawler.analyzer import build_summary, health_score, issue_breakdown
from seo_crawler.report import (
    breakdown_to_dataframe,
    issues_to_dataframe,
    results_to_dataframe,
    summary_to_dataframe,
)

HOSTED = os.getenv("HOSTED", "0") == "1"
MAX_PAGES_CAP = 50 if HOSTED else 500
MIN_DELAY = 0.3 if HOSTED else 0.0

st.set_page_config(
    page_title="Mini SEO Crawler",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.5rem; max-width: 1200px; }
      [data-testid="stMetricValue"] { font-size: 1.6rem; }
      code { font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Sidebar: crawl settings
# ----------------------------------------------------------------------
with st.sidebar:
    st.title("Crawl settings")
    max_pages = st.slider("Pages to crawl", 5, MAX_PAGES_CAP, min(25, MAX_PAGES_CAP), step=5)
    delay = st.slider("Delay between requests (s)", MIN_DELAY, 3.0, max(0.5, MIN_DELAY), 0.1)
    workers = st.slider("Parallel workers", 1, 8, 4)
    max_depth = st.slider("Maximum link depth", 1, 10, 5)

    st.divider()
    exclude_raw = st.text_input(
        "Skip URLs containing", placeholder="/tag/, /author/, ?replytocom"
    )
    include_subdomains = st.checkbox("Also crawl subdomains", value=False)
    respect_robots = st.checkbox(
        "Respect robots.txt", value=True, disabled=HOSTED,
        help="Always on for the hosted demo.",
    )

    st.divider()
    st.caption(f"Mini SEO Crawler v{__version__}")
    st.caption("Only crawl sites you own or have permission to audit.")


# ----------------------------------------------------------------------
# Header + input
# ----------------------------------------------------------------------
st.title("Mini SEO Crawler")
st.write(
    "Crawl a site, extract every on-page SEO element, and download a technical audit "
    "as CSV or Excel."
)

col_url, col_button = st.columns([5, 1])
with col_url:
    url = st.text_input(
        "Website URL", placeholder="https://example.com", label_visibility="collapsed"
    )
with col_button:
    start = st.button("Start crawl", type="primary", width="stretch")


# ----------------------------------------------------------------------
# Crawl
# ----------------------------------------------------------------------
def run_crawl(config: CrawlConfig):
    """Run the crawl while streaming progress into the page."""
    crawler = Crawler(config)
    progress = st.progress(0.0, text="Starting crawl…")
    log_box = st.empty()
    log_lines: list[str] = []

    def on_progress(done: int, total: int, result) -> None:
        code = result.error or result.status_code or "ERR"
        log_lines.append(f"[{done:>3}/{total}]  {code:<6} {result.response_time:>5.2f}s  {result.url}")
        progress.progress(min(done / total, 1.0), text=f"Crawled {done} of {total} pages")
        log_box.code("\n".join(log_lines[-12:]), language="text")

    started = time.perf_counter()
    results = crawler.crawl(on_progress=on_progress)
    elapsed = time.perf_counter() - started

    progress.progress(1.0, text=f"Done — {len(results)} pages in {elapsed:.1f}s")
    log_box.empty()
    return crawler, results, elapsed


if start:
    if not url.strip():
        st.warning("Enter a website URL to crawl.")
    else:
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            target = "https://" + target

        config = CrawlConfig(
            start_url=target,
            max_pages=max_pages,
            max_depth=max_depth,
            delay=delay,
            workers=workers,
            respect_robots=True if HOSTED else respect_robots,
            include_subdomains=include_subdomains,
            include_patterns=[],
            exclude_patterns=[p.strip() for p in exclude_raw.split(",") if p.strip()],
        )

        try:
            crawler, results, elapsed = run_crawl(config)
            st.session_state["results"] = results
            st.session_state["start_url"] = crawler.start_url
            st.session_state["elapsed"] = elapsed
            st.session_state["not_crawled"] = crawler.queued_but_not_crawled
        except ValueError as exc:
            st.error(f"{exc}")
        except Exception as exc:  # network failures, DNS, etc.
            st.error(f"Crawl failed: {exc.__class__.__name__} — {exc}")


# ----------------------------------------------------------------------
# Results
# ----------------------------------------------------------------------
results = st.session_state.get("results")

if results:
    start_url = st.session_state["start_url"]
    summary = build_summary(results)
    score = health_score(results)

    st.subheader("Results")
    row = st.columns(5)
    row[0].metric("SEO health score", f"{score}/100")
    row[1].metric("Pages crawled", summary["Pages crawled"])
    row[2].metric("Indexable", summary["Indexable pages"])
    row[3].metric("Errors (4xx/5xx)", summary["4xx Client error"] + summary["5xx Server error"])
    row[4].metric("Issues found", summary["Total issues found"])

    if st.session_state.get("not_crawled"):
        st.info(
            f"{st.session_state['not_crawled']} more internal URLs were found but not "
            "crawled — raise the page limit to include them."
        )

    tab_pages, tab_issues, tab_breakdown, tab_summary = st.tabs(
        ["Crawl data", "Issues", "Issue breakdown", "Summary"]
    )

    crawl_df = results_to_dataframe(results)
    issues_df = issues_to_dataframe(results)

    with tab_pages:
        only_problems = st.checkbox("Show only pages with issues", value=False)
        view = crawl_df[crawl_df["Issue Count"] > 0] if only_problems else crawl_df
        st.dataframe(view, width="stretch", hide_index=True, height=430)

    with tab_issues:
        if issues_df.empty:
            st.success("No issues found.")
        else:
            severities = st.multiselect(
                "Severity",
                ["Critical", "High", "Medium", "Low"],
                default=["Critical", "High", "Medium"],
            )
            filtered = issues_df[issues_df["Severity"].isin(severities)] if severities else issues_df
            st.dataframe(filtered, width="stretch", hide_index=True, height=430)

    with tab_breakdown:
        breakdown_df = breakdown_to_dataframe(results)
        if breakdown_df.empty:
            st.success("Nothing to report.")
        else:
            chart_data = breakdown_df.set_index("Issue Type")["Pages Affected"].head(12)
            st.bar_chart(chart_data, horizontal=True, height=380)
            st.dataframe(breakdown_df, width="stretch", hide_index=True)

    with tab_summary:
        summary_view = summary_to_dataframe(results, start_url)
        summary_view["Value"] = summary_view["Value"].astype(str)
        st.dataframe(summary_view, width="stretch", hide_index=True, height=430)

    # ---- downloads ----
    st.subheader("Download the report")
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        summary_to_dataframe(results, start_url).to_excel(writer, sheet_name="Summary", index=False)
        crawl_df.to_excel(writer, sheet_name="Crawl Data", index=False)
        issues_df.to_excel(writer, sheet_name="Issues", index=False)
        breakdown_to_dataframe(results).to_excel(writer, sheet_name="Issue Breakdown", index=False)

    dl1, dl2, dl3 = st.columns(3)
    dl1.download_button(
        "Crawl data (CSV)",
        crawl_df.to_csv(index=False).encode("utf-8-sig"),
        "seo_crawl_report.csv",
        "text/csv",
        width="stretch",
    )
    dl2.download_button(
        "Issues (CSV)",
        issues_df.to_csv(index=False).encode("utf-8-sig"),
        "seo_crawl_issues.csv",
        "text/csv",
        width="stretch",
    )
    dl3.download_button(
        "Full report (Excel)",
        excel_buffer.getvalue(),
        "seo_crawl_report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

elif not start:
    st.info("Enter a URL above to run your first crawl.")
    with st.expander("What this checks on every page"):
        st.markdown(
            """
            **Response** — status code, final URL, redirect chain, response time, crawl depth
            **Indexability** — noindex, `X-Robots-Tag`, canonical conflicts, robots.txt blocks
            **Metadata** — title and meta description text, length and duplicates
            **Headings** — H1 text, H1 count, H2 count
            **Links** — internal, external and nofollow counts
            **Images** — total images and images missing ALT text
            **Content** — visible word count, thin-content flag
            **Extras** — `html lang`, viewport, hreflang tags, JSON-LD schema types
            """
        )
