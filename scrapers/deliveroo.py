from __future__ import annotations

from scrapers.base import BaseMenuScraper


class DeliverooScraper(BaseMenuScraper):
    platform_id = "deliveroo"
    platform_name = "Deliveroo"
    url_patterns = ("deliveroo.co.uk", "deliveroo.com", "deliveroo.")
    menu_url_hints = ("menu", "restaurant", "catalog", "items", "basket")

    def matches_url(self, url: str) -> bool:
        lower = url.lower()
        return any(p in lower for p in self.url_patterns)
