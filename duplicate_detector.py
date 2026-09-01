"""Duplicate SEO element detection."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Iterable


def _fingerprint(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip().lower())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def find_duplicates(rows: Iterable[dict], fields: tuple[str, ...] = (
    "title", "meta_description", "h1", "content"
)) -> dict[str, dict[str, list[str]]]:
    """Return duplicate groups for selected fields.

    Each row should contain at least a 'url' key and the selected fields.
    """
    result = {}
    rows = list(rows)

    for field in fields:
        groups = defaultdict(list)
        for row in rows:
            value = row.get(field, "")
            if not value:
                continue
            groups[_fingerprint(str(value))].append(row.get("url", ""))

        duplicates = {
            fingerprint: urls
            for fingerprint, urls in groups.items()
            if len(urls) > 1
        }

        result[field] = duplicates

    return result
