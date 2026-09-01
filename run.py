#!/usr/bin/env python3
"""Convenience entry point: ``python run.py https://example.com --max-pages 50``."""

from seo_crawler.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
