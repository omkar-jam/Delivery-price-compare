"""Platform detection and scraper registry."""

from __future__ import annotations

from pathlib import Path
from typing import Type

import pandas as pd

from scrapers.base import BaseMenuScraper, MenuItem
from scrapers.deliveroo import DeliverooScraper
from scrapers.doordash import DoorDashScraper
from scrapers.generic import GenericScraper
from scrapers.grubhub import GrubhubScraper
from scrapers.just_eat import JustEatScraper
from scrapers.uber_eats import UberEatsScraper

# Order matters: specific platforms before generic fallback.
SCRAPER_CLASSES: tuple[Type[BaseMenuScraper], ...] = (
    UberEatsScraper,
    DoorDashScraper,
    DeliverooScraper,
    GrubhubScraper,
    JustEatScraper,
    GenericScraper,
)

_REGISTRY: dict[str, Type[BaseMenuScraper]] = {
    cls().platform_id: cls for cls in SCRAPER_CLASSES
}


def list_platforms() -> list[dict[str, str]]:
    """Return supported platforms (excludes generic unless requested)."""
    rows = []
    for cls in SCRAPER_CLASSES:
        inst = cls()
        if inst.platform_id == "generic":
            continue
        rows.append(
            {
                "id": inst.platform_id,
                "name": inst.platform_name,
                "url_patterns": ", ".join(inst.url_patterns),
            }
        )
    rows.append(
        {
            "id": GenericScraper().platform_id,
            "name": GenericScraper().platform_name,
            "url_patterns": "any URL (DOM fallback)",
        }
    )
    return rows


def detect_platform(url: str) -> str:
    """Auto-detect platform id from store URL."""
    for cls in SCRAPER_CLASSES:
        if cls is GenericScraper:
            continue
        inst = cls()
        if inst.matches_url(url):
            return inst.platform_id
    return GenericScraper().platform_id


def get_scraper(platform: str | None, url: str) -> BaseMenuScraper:
    """Resolve scraper by explicit platform id or URL auto-detection."""
    if platform:
        key = platform.strip().lower().replace("-", "_")
        if key not in _REGISTRY:
            known = ", ".join(sorted(_REGISTRY))
            raise ValueError(f"Unknown platform '{platform}'. Known: {known}")
        return _REGISTRY[key]()

    platform_id = detect_platform(url)
    return _REGISTRY[platform_id]()


def scrape_url(
    url: str,
    *,
    platform: str | None = None,
    headless: bool = True,
) -> list[MenuItem]:
    scraper = get_scraper(platform, url)
    return scraper.scrape(url, headless=headless)


def save_menu_csv(items: list[MenuItem], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [item.to_dict() for item in items]
    df = pd.DataFrame(rows)
    for col in ("name", "price", "category", "platform", "scraped_at", "source_url"):
        if col not in df.columns:
            df[col] = ""
    df.to_csv(path, index=False)
    return path
