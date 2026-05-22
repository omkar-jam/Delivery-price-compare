"""Pluggable delivery platform menu scrapers."""

from scrapers.registry import detect_platform, get_scraper, list_platforms, scrape_url

__all__ = ["detect_platform", "get_scraper", "list_platforms", "scrape_url"]
