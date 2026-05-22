"""Product-family and category-aware matching helpers."""

from __future__ import annotations

from rapidfuzz import fuzz

from app.utils import normalize_name

# Keywords map to a single product family (checked in name + category text).
FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "omelette": ("omelette", "omlette"),
    "sandwich": ("sandwich", "sandwhich", "daily sandwiches"),
    "bagel": ("bagel", "bagels"),
    "crepe": ("crepe", "crepes", "savoury crepe"),
    "waffle": ("waffle", "waffles"),
    "churros": ("churros", "churro"),
    "pancake": ("pancake", "pancakes", "dutch mini", "mini pancake"),
    "croissant": ("croissant", "croissants", "filled croissant"),
    "panini": ("panini", "ciabatta", "melt panini"),
    "toast": ("sourdough toast", "toast"),
    "coffee": ("coffee", "latte", "cappuccino", "espresso", "mocha", "macchiato", "americano"),
    "tea": ("tea", "chai", "matcha", "bubble tea", "milk tea"),
    "milkshake": ("milkshake", "shake"),
    "cake": ("cake", "brownie", "cheesecake", "gateau", "tart", "muffin"),
    "drink": ("coke", "fanta", "sprite", "water", "juice", "soft drink"),
}

# Pairs that should not match on name similarity alone.
INCOMPATIBLE_FAMILIES: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"sandwich", "omelette"}),
        frozenset({"bagel", "omelette"}),
        frozenset({"crepe", "sandwich"}),
        frozenset({"crepe", "bagel"}),
        frozenset({"croissant", "omelette"}),
        frozenset({"pancake", "omelette"}),
        frozenset({"waffle", "omelette"}),
        frozenset({"coffee", "milkshake"}),
        frozenset({"coffee", "tea"}),
        frozenset({"cake", "coffee"}),
    }
)

# Families that can coexist (e.g. "omelette sandwich").
COMPATIBLE_MULTI: frozenset[str] = frozenset({"omelette", "sandwich"})


def infer_product_families(name: str, category: str = "") -> set[str]:
    """Detect product type(s) from item name and menu section."""
    name_families = explicit_families_in_name(name)
    if name_families:
        return name_families
    cat_text = normalize_name(str(category) if category == category else "")
    if not cat_text:
        return {"unknown"}
    found: set[str] = set()
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(kw in cat_text for kw in keywords):
            found.add(family)
    return found or {"unknown"}


def explicit_families_in_name(name: str) -> set[str]:
    """Families clearly stated in the item title (not just category)."""
    text = normalize_name(name)
    found: set[str] = set()
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.add(family)
    return found


def families_compatible(online_families: set[str], pos_families: set[str]) -> bool:
    if "unknown" in online_families or "unknown" in pos_families:
        return True
    if online_families & pos_families:
        return True
    if online_families <= COMPATIBLE_MULTI and pos_families <= COMPATIBLE_MULTI:
        if online_families & pos_families:
            return True
    for a in online_families:
        for b in pos_families:
            if frozenset({a, b}) in INCOMPATIBLE_FAMILIES:
                return False
    return True


def strict_name_family_ok(online_name: str, online_category: str, pos_name: str) -> bool:
    """
    Reject when POS title embeds a product type missing from the online item.

    Example: online 'Turkey Ham & Cheese' vs POS 'Turkey Ham & Cheese Omelette'.
    """
    pos_explicit = explicit_families_in_name(pos_name)
    if not pos_explicit:
        return True
    online_explicit = explicit_families_in_name(online_name)
    if online_explicit:
        return bool(online_explicit & pos_explicit) or families_compatible(
            online_explicit, pos_explicit
        )
    online_from_cat = infer_product_families("", online_category)
    if "unknown" not in online_from_cat and online_from_cat & pos_explicit:
        return True
    return False


def category_similarity(online_category: str, pos_category: str) -> float:
    a = normalize_name(online_category)
    b = normalize_name(pos_category)
    if not a or not b:
        return 0.0
    return float(fuzz.token_set_ratio(a, b))


def combined_match_score(
    online_name: str,
    online_category: str,
    pos_name: str,
    pos_category: str,
) -> float:
    """0–100 score blending name, category, and product family."""
    online_norm = normalize_name(online_name)
    pos_norm = normalize_name(pos_name)
    if not online_norm or not pos_norm:
        return 0.0

    online_fam = infer_product_families(online_name, online_category)
    pos_fam = infer_product_families(pos_name, pos_category)

    if not families_compatible(online_fam, pos_fam):
        return 0.0
    if not strict_name_family_ok(online_name, online_category, pos_name):
        return 0.0

    name_score = float(fuzz.token_sort_ratio(online_norm, pos_norm))
    cat_score = category_similarity(online_category, pos_category)

    family_bonus = 0.0
    if online_fam & pos_fam and "unknown" not in (online_fam | pos_fam):
        family_bonus = 12.0
    elif online_fam != {"unknown"} and pos_fam != {"unknown"}:
        family_bonus = -8.0

    return min(100.0, name_score * 0.72 + cat_score * 0.18 + family_bonus)
