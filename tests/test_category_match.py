"""Tests for category-aware menu matching."""

from app.category_match import (
    combined_match_score,
    families_compatible,
    infer_product_families,
    strict_name_family_ok,
)


def test_sandwich_vs_omelette_incompatible():
    assert not families_compatible(
        infer_product_families("Turkey Ham & Cheese", "Daily Sandwiches"),
        infer_product_families("Turkey Ham & Cheese Omelette", "Omelette"),
    )


def test_strict_name_rejects_omelette_suffix():
    assert not strict_name_family_ok(
        "Turkey Ham & Cheese",
        "Sandwiches",
        "Turkey Ham & Cheese Omelette",
    )


def test_sandwich_matches_sandwich_pos():
    online = "Turkey Ham & Cheese"
    pos = "Turkey Ham & Cheese Sandwhich"
    assert strict_name_family_ok(online, "Daily Sandwiches", pos)
    score_omelette = combined_match_score(online, "Sandwiches", "Turkey Ham & Cheese Omelette", "Omelette")
    score_sandwich = combined_match_score(online, "Sandwiches", pos, "Daily Sandwiches")
    assert score_sandwich > score_omelette


def test_cheese_tomato_sandwich_not_omelette():
    online = "Cheese & Tomato"
    score_omelette = combined_match_score(online, "Sandwiches", "Cheese Omlette", "Omelette")
    score_croissant = combined_match_score(online, "Sandwiches", "Cheese & Tomato Croissant", "Filled Croissants")
    assert score_omelette == 0.0 or score_croissant >= score_omelette
