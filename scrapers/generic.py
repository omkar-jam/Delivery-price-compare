from __future__ import annotations

from scrapers.base import BaseMenuScraper


class GenericScraper(BaseMenuScraper):
    """DOM-only fallback for unknown delivery sites."""

    platform_id = "generic"
    platform_name = "Generic (DOM fallback)"
    url_patterns = ()
    menu_url_hints = ("menu", "catalog", "items", "product", "store")

    def matches_url(self, url: str) -> bool:
        return True
