from __future__ import annotations

from scrapers.base import BaseMenuScraper


class GrubhubScraper(BaseMenuScraper):
    platform_id = "grubhub"
    platform_name = "Grubhub"
    url_patterns = ("grubhub.com", "seamless.com")
    menu_url_hints = ("menu", "restaurant", "catalog", "item", "graphql")

    def matches_url(self, url: str) -> bool:
        lower = url.lower()
        return any(p in lower for p in self.url_patterns)
