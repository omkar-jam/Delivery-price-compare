"""Base scraper types and Playwright-powered implementation."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from scrapers.utils import dedupe_items, looks_like_menu_payload, parse_price, utc_now_iso, walk_menu_json

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

RATE_LIMIT_SEC = 2.0
DEFAULT_TIMEOUT_MS = 45000


@dataclass
class MenuItem:
    name: str
    price: float | None
    category: str = ""
    platform: str = ""
    scraped_at: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseMenuScraper(ABC):
    """Abstract menu scraper for a delivery platform."""

    platform_id: str = ""
    platform_name: str = ""
    url_patterns: tuple[str, ...] = ()
    menu_url_hints: tuple[str, ...] = ("menu", "catalog", "storefront", "items")
    dom_selectors: tuple[str, ...] = (
        '[data-testid*="menu-item"]',
        '[data-testid*="store-item"]',
        "li[role='listitem']",
        "article",
    )

    @abstractmethod
    def matches_url(self, url: str) -> bool:
        """Return True if this scraper handles the given store URL."""

    def scrape(self, url: str, *, headless: bool = True, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> list[MenuItem]:
        """Scrape menu items: network JSON first, DOM fallback second."""
        from playwright.sync_api import Response, sync_playwright

        captured: list[dict] = []

        def on_response(response: Response) -> None:
            if captured:
                return
            try:
                if response.status != 200:
                    return
                req_url = response.url.lower()
                if not any(h in req_url for h in self.menu_url_hints):
                    return
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" not in ctype and not req_url.endswith(".json"):
                    return
                data = response.json()
                if looks_like_menu_payload(data):
                    raw = walk_menu_json(data)
                    if raw:
                        scraped_at = utc_now_iso()
                        for row in raw:
                            captured.append(
                                {
                                    "name": row["name"],
                                    "price": row["price"],
                                    "category": row.get("category", ""),
                                    "scraped_at": scraped_at,
                                    "platform": self.platform_id,
                                    "source_url": url,
                                }
                            )
            except Exception:
                pass

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                locale="en-GB",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(RATE_LIMIT_SEC)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(RATE_LIMIT_SEC)
            if not captured:
                captured = self._dom_scrape(page, url)
            browser.close()

        deduped = dedupe_items(captured)
        return [
            MenuItem(
                name=row["name"],
                price=row["price"],
                category=row.get("category", ""),
                platform=self.platform_id,
                scraped_at=row.get("scraped_at", utc_now_iso()),
                source_url=url,
            )
            for row in deduped
        ]

    def _dom_scrape(self, page: "Page", url: str) -> list[dict]:
        scraped_at = utc_now_iso()
        items: list[dict] = []
        for sel in self.dom_selectors:
            loc = page.locator(sel)
            count = min(loc.count(), 200)
            if count < 3:
                continue
            for i in range(count):
                el = loc.nth(i)
                try:
                    text = el.inner_text(timeout=500)
                except Exception:
                    continue
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) < 2:
                    continue
                name = lines[0]
                price_line = next(
                    (ln for ln in lines[1:] if re.search(r"[£$€]|\d+\.\d{2}", ln)),
                    lines[1] if len(lines) > 1 else "",
                )
                price = parse_price(price_line)
                if name and price is not None:
                    items.append(
                        {
                            "name": name,
                            "price": price,
                            "category": "",
                            "scraped_at": scraped_at,
                            "platform": self.platform_id,
                            "source_url": url,
                        }
                    )
            if items:
                break
        return dedupe_items(items)
