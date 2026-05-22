from __future__ import annotations

from scrapers.base import BaseMenuScraper


class JustEatScraper(BaseMenuScraper):
    platform_id = "just_eat"
    platform_name = "Just Eat"
    url_patterns = ("just-eat.co.uk", "just-eat.com", "justeat.")
    menu_url_hints = ("menu", "restaurant", "catalog", "items", "api")

    def matches_url(self, url: str) -> bool:
        lower = url.lower()
        return any(p in lower for p in self.url_patterns)
