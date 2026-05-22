"""URL platform detection tests (no live scraping)."""

import pytest

from scrapers.registry import detect_platform, get_scraper, list_platforms


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.ubereats.com/gb/store/foo/abc", "uber_eats"),
        ("https://uber.com/eats/store/foo", "uber_eats"),
        ("https://www.doordash.com/store/foo", "doordash"),
        ("https://www.deliveroo.co.uk/menu/london/foo", "deliveroo"),
        ("https://www.grubhub.com/restaurant/foo", "grubhub"),
        ("https://www.just-eat.co.uk/restaurants/foo", "just_eat"),
        ("https://example-food-site.com/menu", "generic"),
    ],
)
def test_detect_platform(url: str, expected: str) -> None:
    assert detect_platform(url) == expected


def test_get_scraper_force_platform() -> None:
    scraper = get_scraper("deliveroo", "https://unknown.example/menu")
    assert scraper.platform_id == "deliveroo"


def test_list_platforms_includes_known_ids() -> None:
    ids = {row["id"] for row in list_platforms()}
    assert "uber_eats" in ids
    assert "doordash" in ids
    assert "generic" in ids


def test_unknown_platform_raises() -> None:
    with pytest.raises(ValueError, match="Unknown platform"):
        get_scraper("not_a_platform", "https://example.com")
