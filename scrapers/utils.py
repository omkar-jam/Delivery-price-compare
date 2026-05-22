"""Shared scraping utilities: prices, names, dedupe."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

PRICE_RE = re.compile(
    r"(?:£|\$|€)?\s*(\d{1,4}(?:[.,]\d{2})?)|(\d{1,4}(?:[.,]\d{2})?)\s*(?:£|\$|€)",
    re.IGNORECASE,
)
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
SPACE_RE = re.compile(r"\s+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_name(name: str) -> str:
    if not name:
        return ""
    lowered = name.strip().lower()
    no_punct = PUNCT_RE.sub(" ", lowered)
    return SPACE_RE.sub(" ", no_punct).strip()


def parse_price(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = PRICE_RE.search(text.replace(",", "."))
    if not match:
        return None
    num = match.group(1) or match.group(2)
    try:
        return float(num.replace(",", "."))
    except ValueError:
        return None


JUNK_NAME_RE = re.compile(
    r"^#\d+\s+most\s+liked$|^most\s+liked$|^popular$|^bestseller$",
    re.IGNORECASE,
)


def is_junk_menu_name(name: str) -> bool:
    """Filter badge labels mistaken for menu item names."""
    if not name or len(name) < 2:
        return True
    return bool(JUNK_NAME_RE.match(name.strip()))


def dedupe_items(items: list[dict], key: str = "name") -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        norm = normalize_name(str(item.get(key, "")))
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(item)
    return out


def looks_like_menu_payload(data: Any) -> bool:
    if not isinstance(data, (dict, list)):
        return False
    blob = json.dumps(data).lower()
    return any(k in blob for k in ("menuitem", "menu_item", "catalog", "price", "title", "item"))


def walk_menu_json(node: Any, category: str = "") -> list[dict]:
    """Extract name/price pairs from nested menu JSON."""
    found: list[dict] = []
    if isinstance(node, dict):
        cat = category
        for key in ("category", "categoryName", "sectionTitle"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                cat = val.strip()
                break

        title = (
            node.get("title")
            or node.get("name")
            or node.get("displayName")
            or node.get("itemName")
            or node.get("itemDescription")
        )
        price = node.get("price") or node.get("unitPrice") or node.get("formattedPrice")
        if price is None and isinstance(node.get("priceInfo"), dict):
            price = node["priceInfo"].get("amount") or node["priceInfo"].get("price")
        if price is None and isinstance(node.get("purchaseInfo"), dict):
            pi = node["purchaseInfo"].get("priceInfo") or node["purchaseInfo"]
            if isinstance(pi, dict):
                price = pi.get("amount") or pi.get("price")
        if price is None and isinstance(node.get("priceTagline"), str):
            price = node["priceTagline"]
        if title and price is not None:
            parsed = parse_price(price)
            if parsed is not None:
                found.append({"name": str(title).strip(), "price": parsed, "category": cat or ""})

        for key in (
            "sections",
            "categories",
            "items",
            "menuItems",
            "subsections",
            "products",
            "catalogSections",
            "catalogItems",
            "standardItemsPayload",
            "payload",
            "data",
        ):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    found.extend(walk_menu_json(item, str(cat or category)))
            elif isinstance(child, dict):
                found.extend(walk_menu_json(child, str(cat or category)))

        for v in node.values():
            if isinstance(v, (dict, list)):
                found.extend(walk_menu_json(v, str(cat or category)))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_menu_json(item, category))
    return found
