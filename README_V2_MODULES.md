# Mini SEO Crawler V2 — Additional Modules

These modules are designed as an extension layer for the existing Mini SEO Crawler V1.

## Add first
1. `url_normalizer.py`
2. `robots.py`
3. `sitemap.py`
4. `redirect_checker.py`
5. `seo_rules.py`
6. `severity_engine.py`
7. `duplicate_detector.py`
8. `schema_analyzer.py`
9. `hreflang_analyzer.py`
10. `link_analyzer.py`
11. `summary_report.py`

## Dependencies

```bash
pip install requests beautifulsoup4 pandas openpyxl
```

The modules are intentionally separated so they can be integrated into your existing crawler rather than replacing your current V1 files.

## Important

Before pushing these to GitHub, test them against your existing crawler interfaces. They are standalone utilities because the exact V1 repository source files were not provided here.

Do not claim a feature as completed until you have integrated it, tested it, and verified the output.
