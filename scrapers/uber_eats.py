"""Uber Eats scraper: full menu via scroll, category tabs, and JSON capture."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from scrapers.base import BaseMenuScraper, MenuItem
from scrapers.utils import (
    dedupe_items,
    is_junk_menu_name,
    looks_like_menu_payload,
    parse_price,
    utc_now_iso,
    walk_menu_json,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

DEFAULT_TIMEOUT_MS = 90000
SCROLL_PAUSE_SEC = 0.7
MAX_SCROLL_ROUNDS = 50
CATEGORY_CLICK_PAUSE_SEC = 1.2

UBER_DOM_EXTRACT_JS = """
() => {
  const results = [];
  const seen = new Set();
  const junk = /^#\\d+\\s+most\\s+liked$/i;

  function add(name, price, category) {
    name = (name || '').trim();
    if (!name || name.length < 2 || junk.test(name) || seen.has(name)) return;
    const p = parseFloat(String(price).replace(/[^0-9.]/g, ''));
    if (!p || p <= 0 || p > 500) return;
    seen.add(name);
    results.push({ name, price: p, category: category || '' });
  }

  function parseBlock(text, category) {
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) return;
    const name = lines[0];
    const priceLine = lines.find(l => /[£$€]|\\d+[.,]\\d{2}/.test(l)) || lines[1];
    const m = priceLine.match(/(\\d+[.,]\\d{2})/);
    if (m) add(name, m[1].replace(',', '.'), category);
  }

  // Item cards with test ids
  const selectors = [
    '[data-testid="store-item"]',
    '[data-testid*="menu-item"]',
    '[data-testid*="store-menu-item"]',
    'li[data-testid]',
  ];
  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach(el => {
      parseBlock(el.innerText || '', '');
    });
  }

  // Section headings + following siblings (category-aware)
  document.querySelectorAll('h3, h4, [data-testid*="category"]').forEach(heading => {
    const category = (heading.innerText || '').trim().split('\\n')[0];
    let el = heading.nextElementSibling;
    let steps = 0;
    while (el && steps < 40) {
      if (el.matches && (el.matches('h3') || el.matches('h4'))) break;
      const text = el.innerText || '';
      if (text && text.length < 300) parseBlock(text, category);
      el = el.nextElementSibling;
      steps++;
    }
  });

  return results;
}
"""


class UberEatsScraper(BaseMenuScraper):
    platform_id = "uber_eats"
    platform_name = "Uber Eats"
    url_patterns = ("ubereats.com", "uber.com/eats")
    menu_url_hints = (
        "menu",
        "storefront",
        "getstore",
        "getmenu",
        "catalog",
        "eats/v2",
        "catalogitems",
        "eatscatalog",
        "store/v1",
        "getstorev1",
    )
    category_selectors = (
        '[data-testid="store-menu-category"]',
        '[data-testid*="MenuCategory"]',
        'nav[aria-label*="menu" i] button',
        'nav button',
        '[role="tab"]',
    )

    def matches_url(self, url: str) -> bool:
        lower = url.lower()
        return any(p in lower for p in self.url_patterns)

    def scrape(
        self, url: str, *, headless: bool = True, timeout_ms: int = DEFAULT_TIMEOUT_MS
    ) -> list[MenuItem]:
        from playwright.sync_api import sync_playwright

        json_rows: list[dict] = []
        dom_rows: list[dict] = []
        seen_payload_hashes: set[int] = set()

        def on_response(response: Response) -> None:
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
                payload_hash = hash(json.dumps(data, sort_keys=True, default=str)[:8000])
                if payload_hash in seen_payload_hashes:
                    return
                if not looks_like_menu_payload(data):
                    return
                seen_payload_hashes.add(payload_hash)
                scraped_at = utc_now_iso()
                for row in walk_menu_json(data):
                    if is_junk_menu_name(row["name"]):
                        continue
                    json_rows.append(
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
                viewport={"width": 1400, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(2)

            # Dismiss cookie/consent if present
            for sel in (
                'button:has-text("Accept")',
                'button:has-text("Got it")',
                '[data-testid="accept-btn"]',
            ):
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1500):
                        btn.click(timeout=2000)
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            self._scroll_fully(page)
            dom_rows.extend(self._extract_dom(page, url))

            # Uber often shows one category at a time — click through sidebar tabs
            clicked = self._scrape_all_categories(page, url, dom_rows)
            if not clicked:
                self._scroll_fully(page)
                dom_rows.extend(self._extract_dom(page, url))

            browser.close()

        merged = dedupe_items(json_rows + dom_rows)
        merged = [r for r in merged if not is_junk_menu_name(r["name"])]
        return [
            MenuItem(
                name=row["name"],
                price=row["price"],
                category=row.get("category", ""),
                platform=self.platform_id,
                scraped_at=row.get("scraped_at", utc_now_iso()),
                source_url=url,
            )
            for row in merged
        ]

    def _scroll_fully(self, page: Page) -> None:
        prev_count = 0
        stale_rounds = 0
        for _ in range(MAX_SCROLL_ROUNDS):
            page.evaluate(
                """
                () => {
                  const scrollers = [
                    document.querySelector('[data-testid="store-menu"]'),
                    document.querySelector('main'),
                    document.documentElement,
                  ].filter(Boolean);
                  for (const el of scrollers) {
                    el.scrollTop = el.scrollHeight;
                  }
                  window.scrollTo(0, document.body.scrollHeight);
                }
                """
            )
            time.sleep(SCROLL_PAUSE_SEC)
            count = page.evaluate("document.body.scrollHeight")
            if count == prev_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
            prev_count = count

    def _extract_dom(self, page: Page, url: str) -> list[dict]:
        scraped_at = utc_now_iso()
        try:
            raw = page.evaluate(UBER_DOM_EXTRACT_JS)
        except Exception:
            raw = []
        rows = []
        for item in raw or []:
            name = item.get("name", "")
            price = parse_price(item.get("price"))
            if name and price is not None and not is_junk_menu_name(name):
                rows.append(
                    {
                        "name": name,
                        "price": price,
                        "category": item.get("category", ""),
                        "scraped_at": scraped_at,
                        "platform": self.platform_id,
                        "source_url": url,
                    }
                )
        return rows

    def _scrape_all_categories(self, page: Page, url: str, dom_rows: list[dict]) -> bool:
        """Click each menu category tab and collect items. Returns True if tabs found."""
        for sel in self.category_selectors:
            tabs = page.locator(sel)
            count = tabs.count()
            if count < 2:
                continue
            for i in range(count):
                try:
                    tab = tabs.nth(i)
                    label = tab.inner_text(timeout=2000).strip().split("\n")[0]
                    if not label or len(label) > 80:
                        continue
                    tab.click(timeout=3000)
                    time.sleep(CATEGORY_CLICK_PAUSE_SEC)
                    self._scroll_fully(page)
                    for row in self._extract_dom(page, url):
                        row["category"] = row.get("category") or label
                        dom_rows.append(row)
                except Exception:
                    continue
            return True
        return False
