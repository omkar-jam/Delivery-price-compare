"""App-level helpers (re-export scraper utils + column detection)."""

from __future__ import annotations

from scrapers.utils import dedupe_items, normalize_name, parse_price, utc_now_iso

__all__ = ["dedupe_items", "normalize_name", "parse_price", "utc_now_iso", "detect_column"]


def detect_column(columns: list[str], candidates: list[str]) -> str | None:
    lower_map = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for col in columns:
        cl = col.lower().strip()
        for cand in candidates:
            if cand.lower() in cl:
                return col
    return None
