from __future__ import annotations

from scrapers.base import BaseMenuScraper


class DoorDashScraper(BaseMenuScraper):
    platform_id = "doordash"
    platform_name = "DoorDash"
    url_patterns = ("doordash.com", "drd.sh")
    menu_url_hints = ("menu", "store", "catalog", "item", "graphql")

    def matches_url(self, url: str) -> bool:
        lower = url.lower()
        return any(p in lower for p in self.url_patterns)
