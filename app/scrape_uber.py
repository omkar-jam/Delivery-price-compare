"""Deprecated: use scrapers.registry.scrape_url instead."""

from __future__ import annotations

import warnings
from pathlib import Path

from scrapers.registry import save_menu_csv, scrape_url


def scrape_store(url: str, headless: bool = True, timeout_ms: int = 45000) -> list[dict]:
    warnings.warn(
        "app.scrape_uber is deprecated; use scrapers.registry.scrape_url",
        DeprecationWarning,
        stacklevel=2,
    )
    items = scrape_url(url, headless=headless)
    return [item.to_dict() for item in items]


def resolve_store_url(cli_url: str | None = None) -> str:
    import os

    url = cli_url or os.environ.get("UBER_EATS_STORE_URL", "").strip()
    if not url:
        raise ValueError("Store URL required: pass --url or set UBER_EATS_STORE_URL")
    return url


def save_menu_csv_legacy(items: list[dict], path: str | Path) -> Path:
    from scrapers.base import MenuItem

    menu_items = [
        MenuItem(
            name=i["name"],
            price=i.get("price"),
            category=i.get("category", ""),
            platform=i.get("platform", "uber_eats"),
            scraped_at=i.get("scraped_at", ""),
            source_url=i.get("source_url", ""),
        )
        for i in items
    ]
    return save_menu_csv(menu_items, path)
